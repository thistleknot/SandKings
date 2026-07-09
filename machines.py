"""The Machine Age: microcontroller VM, devices, and the tinkering maw.

Governed by SPEC_MACHINE_AGE.md (T28-T40). A QBasic-flavored bounded
register machine (PLC scan cycle: PC resets each tick, REGISTERS PERSIST
- counters, edge detection, and hysteresis are expressible); four
actuator "feats" that each ride an existing sim mechanism; a hill-climb
GP tinkerer that mutates the program and keeps what improves colony
utility (the maw as programmer, bootstrapped from the wreck's demo).

Preconditions: stdlib only; pickles with the sim under the stable module
name. Failure modes: DIV by zero yields 0 (no fault); fuel guarantees
halting; ACT beyond the per-tick budget burns fuel silently.
"""

import random
from typing import Dict, List, Optional, Tuple

VM_FUEL = 64
VM_MAX_INSTR = 32
VM_REGISTERS = 8
VM_ACT_BUDGET = 2
VM_TICK = 5
DEVICE_DURABILITY = 240
DECAY_AMBIENT_INTERVAL = 100
CONTROLLER_DECAY = 1
ACTUATOR_WEAR = {'GATE': 2, 'VALVE': 2, 'BEACON': 2, 'ALARM': 1}
REPAIR_PER_COPPER = 80
REPAIR_AT = 100
RE_OPERATE_TICKS = 400
CHASSIS_SALVAGE = 4
CONDUCTOR_COPPER = 2
CONTACT_GOLD = 1
MAX_CONTROLLERS_PER_COLONY = 2
PROGRAM_REVIEW = 200
TINKER_EPSILON = 0.05
VALVE_FOOD_COST = 15
ALARM_STRENGTH = 3.0

SENSOR_NAMES = ("FOOD", "POP", "SEASON", "ENEMY", "CROPS", "STORM",
                "GOLD", "MAWHP", "CLOCK")
ACTUATOR_NAMES = ("GATE", "VALVE", "ALARM", "BEACON")
OPS = ("NOP", "LET", "MOV", "ADD", "SUB", "MUL", "DIV", "SENSE", "ACT",
       "IFC", "JMP")
CMPS = ("<", "<=", "==", "!=", ">=", ">")

# Instruction tuple: (op, a, b, c) - meaning depends on op (see SPEC T30)
Instr = Tuple[str, int, int, int]


def _wrap16(v: int) -> int:
    return ((int(v) + 32768) % 65536) - 32768


class Controller:
    """One microcontroller: program, persistent registers, tinkerer state."""

    def __init__(self, owner: int, program: Optional[List[Instr]] = None):
        self.owner = owner
        self.program: List[Instr] = list(program or DEMO_PROGRAM)[:VM_MAX_INSTR]
        self.registers = [0] * VM_REGISTERS
        self.durability = DEVICE_DURABILITY
        self.operate_ticks = 0
        self.last_sense: Dict[int, int] = {}
        self.last_acts: List[Tuple[int, int]] = []
        # tinkerer state (T35)
        self.u_ema: Optional[float] = None
        self.reviews = 0
        self.last_outcome = "-"
        self._candidate: Optional[List[Instr]] = None
        self._incumbent: Optional[List[Instr]] = None

    def tick(self, sense, act) -> int:
        """One scan cycle: PC<-0, fuel-bounded; returns ops used (T30)."""
        pc = 0
        fuel = VM_FUEL
        acts_done = 0
        self.last_sense = {}
        self.last_acts = []
        n = len(self.program)
        while pc < n and fuel > 0:
            op, a, b, c = self.program[pc]
            fuel -= 1
            pc += 1
            if op == "NOP":
                continue
            if op == "LET":
                self.registers[a % VM_REGISTERS] = _wrap16(b)
            elif op == "MOV":
                self.registers[a % VM_REGISTERS] = self.registers[b % VM_REGISTERS]
            elif op in ("ADD", "SUB", "MUL", "DIV"):
                ra, rb = a % VM_REGISTERS, b % VM_REGISTERS
                x, y = self.registers[ra], self.registers[rb]
                if op == "ADD":
                    self.registers[ra] = _wrap16(x + y)
                elif op == "SUB":
                    self.registers[ra] = _wrap16(x - y)
                elif op == "MUL":
                    self.registers[ra] = _wrap16(x * y)
                else:
                    self.registers[ra] = _wrap16(x // y) if y != 0 else 0
            elif op == "SENSE":
                port = b % len(SENSOR_NAMES)
                value = int(sense(port))
                self.registers[a % VM_REGISTERS] = _wrap16(value)
                self.last_sense[port] = value
            elif op == "ACT":
                if acts_done < VM_ACT_BUDGET:
                    port = a % len(ACTUATOR_NAMES)
                    value = self.registers[b % VM_REGISTERS]
                    act(port, value)
                    self.last_acts.append((port, value))
                    acts_done += 1
            elif op == "IFC":
                # (IFC, a, b, (cmp_idx, target)) packed as c = cmp_idx*100+target
                ra, rb = a % VM_REGISTERS, b % VM_REGISTERS
                cmp_idx, target = divmod(c, 100)
                x, y = self.registers[ra], self.registers[rb]
                cmp = CMPS[cmp_idx % len(CMPS)]
                hit = ((cmp == "<" and x < y) or (cmp == "<=" and x <= y)
                       or (cmp == "==" and x == y) or (cmp == "!=" and x != y)
                       or (cmp == ">=" and x >= y) or (cmp == ">" and x > y))
                if hit:
                    pc = max(0, min(n - 1, target))
            elif op == "JMP":
                pc = max(0, min(n - 1, a))
        self.operate_ticks += 1
        return VM_FUEL - fuel

    def listing(self) -> List[str]:
        """QBasic-ish disassembly for the manager panel (T36)."""
        lines = []
        for i, (op, a, b, c) in enumerate(self.program):
            num = (i + 1) * 10
            if op == "LET":
                text = f"LET R{a % VM_REGISTERS}, {b}"
            elif op in ("MOV", "ADD", "SUB", "MUL", "DIV"):
                text = f"{op} R{a % VM_REGISTERS}, R{b % VM_REGISTERS}"
            elif op == "SENSE":
                port = b % len(SENSOR_NAMES)
                comment = (f"   ' ={self.last_sense[port]}"
                           if port in self.last_sense else "")
                text = f"SENSE R{a % VM_REGISTERS}, {SENSOR_NAMES[port]}{comment}"
            elif op == "ACT":
                text = f"ACT {ACTUATOR_NAMES[a % len(ACTUATOR_NAMES)]}, R{b % VM_REGISTERS}"
            elif op == "IFC":
                cmp_idx, target = divmod(c, 100)
                text = (f"IF R{a % VM_REGISTERS} {CMPS[cmp_idx % len(CMPS)]}"
                        f" R{b % VM_REGISTERS} GOTO {(target + 1) * 10}")
            elif op == "JMP":
                text = f"GOTO {(a + 1) * 10}"
            else:
                text = "NOP"
            lines.append(f"{num} {text}")
        return lines


def make_if(ra: int, cmp: str, rb: int, target: int) -> Instr:
    """Build a conditional jump (op IFC; c packs cmp*100 + target)."""
    return ("IFC", ra, rb, CMPS.index(cmp) * 100 + max(0, min(31, target)))


# The demo, rebuilt with the proper IFC encoding (replaces the sketch)
DEMO_PROGRAM = [
    ("SENSE", 0, 3, 0),          # 10 SENSE R0, ENEMY
    ("LET", 1, 2, 0),            # 20 LET R1, 2
    make_if(0, ">=", 1, 5),      # 30 IF R0 >= R1 GOTO 60
    ("LET", 2, 0, 0),            # 40 LET R2, 0
    ("JMP", 6, 0, 0),            # 50 GOTO 70
    ("LET", 2, 1, 0),            # 60 LET R2, 1
    ("ACT", 0, 2, 0),            # 70 ACT GATE, R2   (0 open / 1 close)
    make_if(2, "==", 1, 8),      # 80 IF R2 == R1? no: guard alarm on close
    ("ACT", 2, 2, 0),            # 90 ACT ALARM, R2  (only reached when closing)
]


class Device:
    """A built actuator: kind, linked position, durability (T32/T33)."""

    def __init__(self, kind: str, owner: int,
                 position: Optional[Tuple[int, int, int]] = None):
        self.kind = kind
        self.owner = owner
        self.position = position
        self.durability = DEVICE_DURABILITY
        self.gate_cells: List[Tuple[int, int, int]] = []  # GATE bookkeeping
        self.gate_closed = False


class GPTinkerer:
    """Hill-climb program mutation, keep-if-improved (T35)."""

    def propose(self, program: List[Instr],
                rng: Optional[random.Random] = None) -> List[Instr]:
        rng = rng or random
        if rng.random() < TINKER_EPSILON or not program:
            return self._random_program(rng)
        candidate = [tuple(i) for i in program]
        roll = rng.random()
        idx = rng.randrange(len(candidate))
        op, a, b, c = candidate[idx]
        if roll < 0.35 and op == "LET":  # tweak constant
            delta = rng.choice((1, -1, 5, -5, 25, -25))
            candidate[idx] = (op, a, _wrap16(b + delta), c)
        elif roll < 0.50:  # retarget a port
            if op == "SENSE":
                candidate[idx] = (op, a, rng.randrange(len(SENSOR_NAMES)), c)
            elif op == "ACT":
                candidate[idx] = (op, rng.randrange(len(ACTUATOR_NAMES)), b, c)
            else:
                candidate[idx] = self._random_instr(rng, len(candidate))
        elif roll < 0.65:  # swap opcode/operand
            candidate[idx] = self._random_instr(rng, len(candidate))
        elif roll < 0.75 and len(candidate) >= 2:  # swap two instructions
            j = rng.randrange(len(candidate))
            candidate[idx], candidate[j] = candidate[j], candidate[idx]
        elif roll < 0.90 and len(candidate) < VM_MAX_INSTR:  # insert
            candidate.insert(idx, self._random_instr(rng, len(candidate) + 1))
        elif len(candidate) > 1:  # delete
            del candidate[idx]
        return candidate

    def _random_instr(self, rng, length: int) -> Instr:
        op = rng.choice(("LET", "MOV", "ADD", "SUB", "SENSE", "ACT",
                         "IFC", "JMP", "NOP"))
        if op == "LET":
            return (op, rng.randrange(VM_REGISTERS),
                    rng.randint(-100, 400), 0)
        if op in ("MOV", "ADD", "SUB"):
            return (op, rng.randrange(VM_REGISTERS),
                    rng.randrange(VM_REGISTERS), 0)
        if op == "SENSE":
            return (op, rng.randrange(VM_REGISTERS),
                    rng.randrange(len(SENSOR_NAMES)), 0)
        if op == "ACT":
            return (op, rng.randrange(len(ACTUATOR_NAMES)),
                    rng.randrange(VM_REGISTERS), 0)
        if op == "IFC":
            return make_if(rng.randrange(VM_REGISTERS),
                           rng.choice(CMPS),
                           rng.randrange(VM_REGISTERS),
                           rng.randrange(max(1, length)))
        if op == "JMP":
            return (op, rng.randrange(max(1, length)), 0, 0)
        return ("NOP", 0, 0, 0)

    def _random_program(self, rng) -> List[Instr]:
        length = rng.randint(4, 8)
        return [self._random_instr(rng, length) for _ in range(length)]
