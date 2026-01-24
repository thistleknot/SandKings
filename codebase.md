# Table of Contents
- corewar_util.py
- drq.py
- eval_warriors.py
- experiment_utils.py
- llm.py
- llm_async.py
- llm_corewar.py
- util.py
- corewar\.travis.yml
- corewar\graphics_random.py
- corewar\graphics_rounds.py
- corewar\LICENSE
- corewar\llm_evolve.py
- corewar\pyproject.toml
- corewar\README.md
- corewar\tests.py
- corewar\corewar\core.py
- corewar\corewar\graphics.py
- corewar\corewar\mars.py
- corewar\corewar\redcode.py
- corewar\corewar\viz.py
- corewar\corewar\__init__.py
- corewar\docs\icws94.txt
- corewar\tests\mars_test.py
- corewar\tests\redcode_test.py
- corewar\tests\__init__.py
- prompts\crossover_prompt_0.txt
- prompts\mutate_prompt_0.txt
- prompts\new_prompt_0.txt
- prompts\system_prompt_0.txt

## File: corewar_util.py

- Extension: .py
- Language: python
- Size: 5005 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
from dataclasses import dataclass
import random
import numpy as np
from functools import partial
from tqdm import tqdm
from multiprocessing import Pool

from corewar import MARS, Core, redcode

@dataclass
class SimulationArgs:
    rounds: int = 24 # Rounds to play
    size: int = 8000 # The core size
    cycles: int = 80000 # Cycles until tie
    processes: int = 8000 # Max processes
    length: int = 100 # Max warrior length
    distance: int = 100 # Minimum warrior distance

def simargs_to_environment(args):
    return dict(ROUNDS=args.rounds, CORESIZE=args.size, CYCLES=args.cycles,
                MAXPROCESSES=args.processes, MAXLENGTH=args.length, MINDISTANCE=args.distance)

class MyMARS(MARS):
    def __init__(self, core=None, warriors=None, minimum_separation=100, randomize=True, max_processes=None):
        self.core = core if core else Core()
        self.minimum_separation = minimum_separation
        self.max_processes = max_processes if max_processes else len(self.core)
        self.warriors = warriors if warriors else []
        self.warrior_cov = {w: np.zeros(len(self.core), dtype=bool) for w in self.warriors}
        # self.warrior_tsp = {w: 0 for w in self.warriors}  # total spawned processes

        if self.warriors:
            self.load_warriors(randomize)

    def core_event(self, warrior, address, event_type):
        i = self.core[address]
        assert isinstance(i.a_number, int), f"Expected int but got {type(i.a_number)}"
        assert isinstance(i.b_number, int), f"Expected int but got {type(i.b_number)}"
        i.a_number = min(max(i.a_number, -999999999), 999999999)
        i.b_number = min(max(i.b_number, -999999999), 999999999)
        assert i.a_number < 1000000000 and i.a_number > -1000000000, f"a_number out of bounds"
        assert i.b_number < 1000000000 and i.b_number > -1000000000, f"b_number out of bounds"
    
    def enqueue(self, warrior, address):
        """Enqueue another process into the warrior's task queue. Only if it's
           not already full.
        """
        if len(warrior.task_queue) < self.max_processes:
            warrior.task_queue.append(self.core.trim(address))
            self.warrior_cov[warrior][self.core.trim(address)] = True
            # self.warrior_tsp[warrior] += 1

def run_single_round(simargs, warriors, seed, pbar=False):
    random.seed(seed)
    simulation = MyMARS(warriors=warriors, minimum_separation=simargs.distance, max_processes=simargs.processes, randomize=True)
    score = np.zeros(len(warriors), dtype=float)
    alive_score = np.zeros(len(warriors), dtype=float)

    prev_nprocs = np.array([len(w.task_queue) for w in simulation.warriors], dtype=int)
    total_spawned_procs = np.zeros(len(simulation.warriors), dtype=int)

    # memory_coverage = [set(w.task_queue) for w in simulation.warriors]
    for t in tqdm(range(simargs.cycles), disable=not pbar):
        simulation.step()

        nprocs = np.array([len(w.task_queue) for w in simulation.warriors], dtype=int)

        alive_flags = (nprocs>0).astype(int)
        n_alive = alive_flags.sum()
        if n_alive==0:
            break
        score += (alive_flags * (1./n_alive)) / simargs.cycles
        alive_score += alive_flags / simargs.cycles

        total_spawned_procs = total_spawned_procs + np.maximum(0, nprocs - prev_nprocs)
        prev_nprocs = nprocs

        # memory_coverage = [mc.union(set(w.task_queue)) for mc, w in zip(memory_coverage, simulation.warriors)]
    # memory_coverage = np.array([len(mc) for mc in memory_coverage], dtype=int)
    memory_coverage = np.array([cov.sum() for cov in simulation.warrior_cov.values()], dtype=int)
    score = score * len(warriors)
    outputs = dict(score=score, alive_score=alive_score, total_spawned_procs=total_spawned_procs, memory_coverage=memory_coverage)
    return outputs

def run_multiple_rounds(simargs, warriors, n_processes=1, timeout=900):
    try:
        run_single_round_fn = partial(run_single_round, simargs, warriors)
        seeds = list(range(simargs.rounds))
        # print("Launching pool")
        with Pool(processes=n_processes) as pool:
            # outputs = pool.map(run_single_round_fn, seeds)
            result = pool.map_async(run_single_round_fn, seeds)
            # print("Blocking and waiting for results")
            outputs = result.get(timeout=timeout)  # Timeout in seconds
        outputs = {k: np.stack([o[k] for o in outputs], axis=-1) for k in outputs[0].keys()}
        # print("Got results!")
        return outputs # shape: (len(warriors), simargs.rounds)
    except Exception as e:
        print(e)
        return None

def parse_warrior_from_file(simargs, file):
    environment = simargs_to_environment(simargs)
    with open(file, encoding="latin1") as f:
        warrior_str = f.read()
    warrior = redcode.parse(warrior_str.split("\n"), environment)
    return warrior_str, warrior


```

## File: drq.py

- Extension: .py
- Language: python
- Size: 12598 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python

import re
import random
import os
import numpy as np
import time
import hashlib
import os
import psutil
import copy

from dataclasses import dataclass, field
import tyro
import asyncio
from tqdm.auto import tqdm
from collections import defaultdict

from llm_corewar import CorewarGPT, GPTWarrior

from corewar_util import SimulationArgs, simargs_to_environment, parse_warrior_from_file, run_multiple_rounds
from corewar import MARS, Warrior
import util

@dataclass
class Args:
    # General arguments
    seed: int = 0
    save_dir: str | None = None
    n_processes: int = 24
    resume: bool | None = False # resume training from save_dir if it exists
    job_timeout: int = 24 * 60 * 60 # entire job timeout in seconds

    # Core War arguments
    simargs: SimulationArgs = field(default_factory=SimulationArgs) # Simulation arguments
    timeout: int = 900 # timeout for each simulation in seconds

    # DRQ arguments
    initial_opps: list[str] = field(default_factory=list) # list of initial opponents
    n_rounds: int = 10 # number of ruonds of DRQ
    n_iters: int = 100 # iterations of evolution per round
    log_every: int = 10 # log every n iterations
    last_k_opps: int | None = None # number of previous rounds' champions to use for current round
    sample_new_percent: float = 0.1 # probability of sampling a new warrior from LLM
    bc_axes: str = "tsp,mc" # comma separated list of two bc axes to use
    # crossover_prob: float = 0.0 # probability of crossover
    warmup_with_init_opps: bool | None = False
    warmup_with_past_champs: bool | None = False
    n_init: int = 8 # number of initial warriors
    n_mutate: int = 1 # number of mutated warriors
    fitness_threshold: float = 0.8 # if this fitness is not reached, continue to next round
    single_cell: bool | None = False # for testing: only use one cell in map elites

    # LLM arguments
    gpt_model: str = "gpt-4.1-mini-2025-04-14" # The GPT model to use
    temperature: float = 1.0
    system_prompt: str = os.path.expanduser("./prompts/system_prompt_0.txt")
    new_prompt: str = os.path.expanduser("./prompts/new_prompt_0.txt")
    mutate_prompt: str = os.path.expanduser("./prompts/mutate_prompt_0.txt")

class MapElites:
    def __init__(self):
        self.archive = {} # bc -> phenotype
        self.history = [] # list of phenotypes which were placed

        self.coverage_history = [] # history of coverage at every place step
        self.fitness_history = [] # history of best fitness in the archive at every place step

    def sample(self):
        random_key = random.choice(list(self.archive.keys()))
        return self.archive[random_key]

    def place(self, phenotype):
        place = (phenotype.bc is not None) and (phenotype.fitness is not None)
        place = place and ((phenotype.bc not in self.archive) or (phenotype.fitness > self.archive[phenotype.bc].fitness))
        if place:
            self.archive[phenotype.bc] = phenotype
        self.history.append(phenotype)
        self.coverage_history.append(len(self.archive))
        self.fitness_history.append(self.get_best().fitness if len(self.archive) > 0 else -np.inf)
        return place
    
    def get_best(self):
        best_key, best_fitness = None, -np.inf
        for k, v in self.archive.items():
            if v.fitness > best_fitness:
                best_key, best_fitness = k, v.fitness
        return self.archive[best_key] if best_key in self.archive else None

class Main:
    """
    This is the main class to run DRQ.
    """
    def __init__(self, args: Args):
        self.args = args
        print(args)
        nproc = os.popen("nproc").read().strip()
        nproc_all = os.popen("nproc --all").read().strip()
        print(f"Number of cores: {nproc} / {nproc_all}")

        random.seed(args.seed)
        np.random.seed(args.seed)

        with open(args.system_prompt, "r") as f:
            system_prompt = f.read()
        with open(args.new_prompt, "r") as f:
            new_warrior_prompt = f.read()
        with open(args.mutate_prompt, "r") as f:
            mutate_warrior_prompt = f.read()
        # with open(args.crossover_prompt, "r") as f:
            # task_crossover_warrior = f.read()

        self.corewar_gpt = CorewarGPT(args.gpt_model, system_prompt, new_warrior_prompt, mutate_warrior_prompt,
                                      temperature=args.temperature, environment=simargs_to_environment(args.simargs))

        self.init_opps = []
        for file in args.initial_opps:
            warrior_str, warrior = parse_warrior_from_file(args.simargs, file)
            gpt_warrior = GPTWarrior(prompt=file, llm_response=warrior_str, warrior=warrior)
            gpt_warrior.id = hashlib.sha256(gpt_warrior.llm_response.encode()).hexdigest()
            self.init_opps.append(gpt_warrior)
        print(f"Loaded {len(self.init_opps)} opponent warriors")

        self.timestamps = []
        self.all_rounds_map_elites = {i_round: MapElites() for i_round in range(self.args.n_rounds)} # map elites of each round
    
    def get_fitness(self, phenotype):
        return phenotype.outputs["score"].item()

    def get_bc_features(self, phenotype):
        if self.args.single_cell:
            return (0, 0)
        if phenotype.outputs is None:
            return (0, 0)
        tsp, mc = phenotype.outputs['total_spawned_procs'].item(), phenotype.outputs['memory_coverage'].item()
        unique_opcodes = len({i.opcode for i in phenotype.warrior.instructions})
        program_len = len(phenotype.warrior.instructions)

        for bc, a in enumerate([1, 10, 100, 1000, 10000, np.inf]):
            if tsp < a:
                bc_tsp = bc
                break
        
        for bc, a in enumerate([10, 100, 500, 1000, 4000, np.inf]):
            if mc < a:
                bc_mc = bc
                break

        for bc, a in enumerate([4, 6, 8, 10, 14, np.inf]):
            if unique_opcodes < a:
                bc_uo = bc
                break

        for bc, a in enumerate([5, 12, 20, 35, 60, np.inf]):
            if program_len < a:
                bc_pl = bc
                break
        all_bcs = dict(tsp=bc_tsp, mc=bc_mc, uo=bc_uo, pl=bc_pl)
        bc1, bc2 = self.args.bc_axes.split(",")
        bc1 = all_bcs[bc1]
        bc2 = all_bcs[bc2]
        # print(f"bc1: {bc1}, bc2: {bc2}")
        return (bc1, bc2)

    def process_warrior(self, i_round, gpt_warrior):
        gpt_warrior = copy.deepcopy(gpt_warrior)
        map_elites = self.all_rounds_map_elites[i_round]
        # print(f"Processing with {list(range(i_round))} prev champs")
        prev_champs = [self.all_rounds_map_elites[i].get_best() for i in range(i_round)]
        # print([p is None for p in prev_champs])
        prev_champs = prev_champs[-self.args.last_k_opps:] if self.args.last_k_opps is not None else prev_champs
        # print("processing with previous champions:")
        # print([f"{pc.warrior.name}, {pc.fitness}" for pc in prev_champs])

        if gpt_warrior.warrior is None:
            gpt_warrior.bc, gpt_warrior.fitness = None, -np.inf
        else:
            opps = self.init_opps + prev_champs
            warriors = [w.warrior for w in [gpt_warrior, *opps]]
            outputs = run_multiple_rounds(self.args.simargs, warriors, n_processes=self.args.n_processes, timeout=self.args.timeout)
            if outputs is None:
                gpt_warrior.bc, gpt_warrior.fitness = None, -np.inf
            else:
                gpt_warrior.outputs = {k: v.mean(axis=-1)[0] for k, v in outputs.items()}
                gpt_warrior.fitness = self.get_fitness(gpt_warrior)
                # gpt_warrior.fitness = self.get_fitness(gpt_warrior) * len(warriors) # normalize the fitness by the number of opponents
                gpt_warrior.bc = self.get_bc_features(gpt_warrior)
                # print(f"Processed Warrrior {gpt_warrior.warrior.name} with fitness {gpt_warrior.fitness} and bc {gpt_warrior.bc}")
        map_elites.place(gpt_warrior)

    def init_round(self, i_round):
        initial_gpt_warriors = asyncio.run(self.corewar_gpt.new_warrior_async(n_warriors=1, n_responses=self.args.n_init)).flatten()
        for w in initial_gpt_warriors:
            self.process_warrior(i_round, w)

        if self.args.warmup_with_init_opps:
            for w in self.init_opps:
                self.process_warrior(i_round, w)
        if self.args.warmup_with_past_champs:
            prev_champs = [self.all_rounds_map_elites[i].get_best() for i in range(i_round)]
            prev_champs = prev_champs[-self.args.last_k_opps:] if self.args.last_k_opps is not None else prev_champs
            for w in prev_champs:
                self.process_warrior(i_round, w)

    def step(self, i_round):
        if random.random() < self.args.sample_new_percent or len(self.all_rounds_map_elites[i_round].archive) == 0:
            gpt_warriors = asyncio.run(self.corewar_gpt.new_warrior_async(n_warriors=1, n_responses=self.args.n_mutate)).flatten()
            for w in gpt_warriors:
                self.process_warrior(i_round, w)
        else:
            gpt_warrior = self.all_rounds_map_elites[i_round].sample()
            gpt_warriors_mutated = asyncio.run(self.corewar_gpt.mutate_warrior_async([gpt_warrior], n_responses=self.args.n_mutate)).flatten()
            for w in gpt_warriors_mutated:
                self.process_warrior(i_round, w)
    
    def run(self):
        this_job_start_time = time.time()
        if self.args.resume and os.path.exists(f"{self.args.save_dir}/args.pkl"):
            self.timestamps = util.load_pkl(self.args.save_dir, "timestamps")
            self.all_rounds_map_elites = util.load_pkl(self.args.save_dir, "all_rounds_map_elites")
            self.corewar_gpt.all_generations = util.load_pkl(self.args.save_dir, "all_generations")
            print(f"Resumed training from {self.args.save_dir}")

            start_abs_iter = self.timestamps[-1]["abs_iter"] + 1 # start from the next iteration
        else:
            start_abs_iter = 0

        pbar = tqdm(range(start_abs_iter, self.args.n_rounds * self.args.n_iters))
        for abs_iter in pbar:
            i_round, i_iter = abs_iter // self.args.n_iters, abs_iter % self.args.n_iters
            # print(f"Starting {abs_iter=}, {i_round=}, {i_iter=}")
            start_time = time.time()

            me = self.all_rounds_map_elites[i_round]
            best_fitness = me.get_best().fitness if len(me.archive) > 0 else -np.inf
            should_skip = best_fitness > self.args.fitness_threshold

            if not should_skip:
                if i_iter == 0:
                    self.init_round(i_round)
                self.step(i_round)

            process = psutil.Process(os.getpid())
            rss = process.memory_info().rss  # Resident Set Size: memory used in bytes
            vms = process.memory_info().vms  # Virtual Memory Size: total virtual memory used in bytes
            self.timestamps.append(dict(abs_iter=abs_iter, i_round=i_round, i_iter=i_iter, dt=time.time()-start_time, rss=rss, vms=vms))

            if abs_iter % self.args.log_every == 0:
                self.save()
            
            if len(me.archive) > 0:
                pbar.set_postfix(best_fitness=me.get_best().fitness)

            if (time.time() - this_job_start_time) > self.args.job_timeout:
                break # manual stop after to avoid slurm job timeout
        self.save()
    
    def save(self):
        if self.args.save_dir is not None:
            util.save_pkl(self.args.save_dir, "args", self.args)
            util.save_pkl(self.args.save_dir, "timestamps", self.timestamps)
            util.save_pkl(self.args.save_dir, "all_rounds_map_elites", self.all_rounds_map_elites)
            util.save_pkl(self.args.save_dir, "all_generations", self.corewar_gpt.all_generations)
            for i_round, me in self.all_rounds_map_elites.items():
                if len(me.archive) > 0:
                    champion = me.get_best()
                    code = re.sub(r"```.*", "", champion.llm_response) # remove the backticks and language tag
                    with open(f"{self.args.save_dir}/round_{i_round:03d}_champion.red", "w") as f:
                        f.write(code)

if __name__ == "__main__":
    main = Main(tyro.cli(Args))
    main.run()
    
```

## File: eval_warriors.py

- Extension: .py
- Language: python
- Size: 1796 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python

import re
import random
import os
import numpy as np
import glob

from dataclasses import dataclass, field
import tyro
import asyncio
from tqdm.auto import tqdm
from collections import defaultdict

from llm_corewar import CorewarGPT, GPTWarrior

from corewar_util import SimulationArgs, simargs_to_environment, parse_warrior_from_file, run_multiple_rounds
from corewar import MARS, Warrior
import util

@dataclass
class Args:
    # General arguments
    seed: int = 0
    save_dir: str | None = None
    n_processes: int = 24

    # Core War arguments
    simargs: SimulationArgs = field(default_factory=SimulationArgs) # Simulation arguments
    timeout: int = 900 # timeout for each simulation in seconds

    warrior_path: str | None = None
    opponents_path_glob: str | None = None

def main(args: Args):
    print(args)
    nproc = os.popen("nproc").read().strip()
    nproc_all = os.popen("nproc --all").read().strip()
    print(f"Number of cores: {nproc} / {nproc_all}")

    random.seed(args.seed)
    np.random.seed(args.seed)

    _, warrior = parse_warrior_from_file(args.simargs, args.warrior_path)
    results = {}

    files = sorted(glob.glob(args.opponents_path_glob))
    for i, file in enumerate(tqdm(files)):
        _, warrior2 = parse_warrior_from_file(args.simargs, file)
        outputs = run_multiple_rounds(args.simargs, [warrior, warrior2], n_processes=args.n_processes, timeout=args.timeout)
        results[(args.warrior_path, file)] = outputs
        if args.save_dir is not None and i % 10 == 0:
            util.save_pkl(args.save_dir, "results", results)
    if args.save_dir is not None:
        util.save_pkl(args.save_dir, "results", results)

if __name__ == "__main__":
    main(tyro.cli(Args))
    

```

## File: experiment_utils.py

- Extension: .py
- Language: python
- Size: 3177 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
import copy
# import itertools
import dataclasses

def dataclass_to_flat_dict(args):
    """
    Converts a tyro dataclass to a flat dictionary.
    """
    a = {}
    for k, v in vars(args).items():
        if v is None or isinstance(v, int) or isinstance(v, float) or isinstance(v, str) or isinstance(v, bool) or isinstance(v, list) or isinstance(v, tuple):
            a[k] = v
        else:
            assert dataclasses.is_dataclass(v), "v is not a dataclass"
            aa = dataclass_to_flat_dict(v)
            for kk, vv in aa.items():
                a[f"{k}.{kk}"] = vv
    return a

# def dict_product(data, product_keys=None):
#     if product_keys is None:
#         product_keys = {k for k, v in data.items() if isinstance(v, list)}
#     data = {k: (v if k in product_keys else [v]) for k, v in data.items()}
#     # data = {key: (val if isinstance(val, list) else [val]) for key, val in data.items()}
#     return [dict(zip(data, vals)) for vals in itertools.product(*data.values())]

def align_configs(cfgs, default_cfg, prune=True):
    """
    Makes sure all cfgs have the default keys.
    Prunes away keys where all cfgs have the default val.
    """
    cfgs = copy.deepcopy(cfgs)
    for k in default_cfg.keys():  # make sure all cfgs have the default keys
        for cfg in cfgs:
            if k not in cfg:
                cfg[k] = default_cfg[k]
    # assert all(c.keys() == default_config.keys() for c in configs)
    if prune:  # prune away keys where all cfgs have the default val
        for k in default_cfg.keys():
            if all([cfg[k] == default_cfg[k] for cfg in cfgs]):
                for cfg in cfgs:
                    del cfg[k]
    return cfgs


def _create_arg_list(cfg):
    def format_value(v):
        return f'"{v}"' if isinstance(v, str) else str(v)

    arg_list = []
    for key, val in cfg.items():
        if isinstance(val, list):
            arg_list.append(f'--{key} {" ".join([format_value(v) for v in val])}')
        else:
            arg_list.append(f"--{key}={format_value(val)}")
    return arg_list


def _create_commands_from_arg_lists(arg_lists, prefix=None):
    n_coms, n_args = len(arg_lists), len(arg_lists[0])
    arg_lens = [max([len(arg_lists[i_com][i_arg]) for i_com in range(n_coms)]) for i_arg in range(n_args)]
    commands = [" ".join([arg_lists[i_com][i_arg].ljust(arg_lens[i_arg]) for i_arg in range(n_args)]) for i_com in
                range(n_coms)]
    if prefix is not None:
        commands = [f"{prefix} {com}" for com in commands]
    return commands


def create_commands(cfgs, prefix=None, out_file=None):
    if dataclasses.is_dataclass(cfgs[0]):
        cfgs = [dataclass_to_flat_dict(cfg) for cfg in cfgs]
    
    assert all([set(cfg.keys()) == set(cfgs[0].keys()) for cfg in cfgs])  # make sure all cfgs have the same keys
    arg_lists = [_create_arg_list(config) for config in cfgs]
    commands = _create_commands_from_arg_lists(arg_lists, prefix=prefix)
    if out_file is not None:
        with open(out_file, "w") as f:
            f.write("\n".join(commands) + "\n")
    return commands

```

## File: llm.py

- Extension: .py
- Language: python
- Size: 12320 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
import json
import os
import re

import anthropic
import backoff
import openai
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

MAX_NUM_TOKENS = 4096

AVAILABLE_LLMS = [
    # Anthropic models
    "claude-3-5-sonnet-20240620",
    "claude-3-5-sonnet-20241022",
    # OpenAI models
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    "gpt-4o",
    "gpt-4o-2024-05-13",
    "gpt-4o-2024-08-06",
    "gpt-4.1",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-mini",
    "gpt-4.1-mini-2025-04-14",
    "gpt-4.1-nano",
    "gpt-4.1-nano-2025-04-14",
    "o1",
    "o1-2024-12-17",
    "o1-preview-2024-09-12",
    "o1-mini",
    "o1-mini-2024-09-12",
    "o3-mini",
    "o3-mini-2025-01-31",
    # OpenRouter models
    "llama3.1-405b",
    # Anthropic Claude models via Amazon Bedrock
    "bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
    "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0",
    "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
    "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
    "bedrock/anthropic.claude-3-opus-20240229-v1:0",
    # Anthropic Claude models Vertex AI
    "vertex_ai/claude-3-opus@20240229",
    "vertex_ai/claude-3-5-sonnet@20240620",
    "vertex_ai/claude-3-5-sonnet-v2@20241022",
    "vertex_ai/claude-3-sonnet@20240229",
    "vertex_ai/claude-3-haiku@20240307",
    # DeepSeek models
    "deepseek-chat",
    "deepseek-coder",
    "deepseek-reasoner",
    # Google Gemini models
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-thinking-exp-01-21",
    "gemini-2.5-pro-preview-03-25",
    "gemini-2.5-pro-exp-03-25",
]


# Get N responses from a single message, used for ensembling.
@backoff.on_exception(backoff.expo, (openai.RateLimitError, openai.APITimeoutError))
def get_batch_responses_from_llm(
        msg,
        client,
        model,
        system_message,
        print_debug=False,
        msg_history=None,
        temperature=0.75,
        n_responses=1,
):
    if msg_history is None:
        msg_history = []

    if 'gpt' in model:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_NUM_TOKENS,
            n=n_responses,
            stop=None,
            seed=0,
        )
        content = [r.message.content for r in response.choices]
        new_msg_history = [
            new_msg_history + [{"role": "assistant", "content": c}] for c in content
        ]
    elif model == "llama-3-1-405b-instruct":
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model="meta-llama/llama-3.1-405b-instruct",
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_NUM_TOKENS,
            n=n_responses,
            stop=None,
        )
        content = [r.message.content for r in response.choices]
        new_msg_history = [
            new_msg_history + [{"role": "assistant", "content": c}] for c in content
        ]
    else:
        content, new_msg_history = [], []
        for _ in range(n_responses):
            c, hist = get_response_from_llm(
                msg,
                client,
                model,
                system_message,
                print_debug=False,
                msg_history=None,
                temperature=temperature,
            )
            content.append(c)
            new_msg_history.append(hist)

    if print_debug:
        print()
        print("*" * 20 + " LLM START " + "*" * 20)
        for j, msg in enumerate(new_msg_history[0]):
            print(f'{j}, {msg["role"]}: {msg["content"]}')
        print(content)
        print("*" * 21 + " LLM END " + "*" * 21)
        print()

    return content, new_msg_history


@backoff.on_exception(backoff.expo, (openai.RateLimitError, openai.APITimeoutError))
def get_response_from_llm(
        msg,
        client,
        model,
        system_message,
        print_debug=False,
        msg_history=None,
        temperature=0.75,
):
    if msg_history is None:
        msg_history = []

    if "claude" in model:
        new_msg_history = msg_history + [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": msg,
                    }
                ],
            }
        ]
        response = client.messages.create(
            model=model,
            max_tokens=MAX_NUM_TOKENS,
            temperature=temperature,
            system=system_message,
            messages=new_msg_history,
        )
        content = response.content[0].text
        new_msg_history = new_msg_history + [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": content,
                    }
                ],
            }
        ]
    elif 'gpt' in model:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_NUM_TOKENS,
            n=1,
            stop=None,
            seed=0,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
    elif "o1" in model or "o3" in model:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": system_message},
                *new_msg_history,
            ],
            temperature=1,
            max_completion_tokens=MAX_NUM_TOKENS,
            n=1,
            seed=0,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
    elif model in ["meta-llama/llama-3.1-405b-instruct", "llama-3-1-405b-instruct"]:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model="meta-llama/llama-3.1-405b-instruct",
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_NUM_TOKENS,
            n=1,
            stop=None,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
    elif model in ["deepseek-chat", "deepseek-coder"]:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_NUM_TOKENS,
            n=1,
            stop=None,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
    elif model in ["deepseek-reasoner"]:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            n=1,
            stop=None,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
    elif "gemini" in model:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_NUM_TOKENS,
            n=1,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
    else:
        raise ValueError(f"Model {model} not supported.")

    if print_debug:
        print()
        print("*" * 20 + " LLM START " + "*" * 20)
        for j, msg in enumerate(new_msg_history):
            print(f'{j}, {msg["role"]}: {msg["content"]}')
        print(content)
        print("*" * 21 + " LLM END " + "*" * 21)
        print()

    return content, new_msg_history


def extract_json_between_markers(llm_output):
    # Regular expression pattern to find JSON content between ```json and ```
    json_pattern = r"```json(.*?)```"
    matches = re.findall(json_pattern, llm_output, re.DOTALL)

    if not matches:
        # Fallback: Try to find any JSON-like content in the output
        json_pattern = r"\{.*?\}"
        matches = re.findall(json_pattern, llm_output, re.DOTALL)

    for json_string in matches:
        json_string = json_string.strip()
        try:
            parsed_json = json.loads(json_string)
            return parsed_json
        except json.JSONDecodeError:
            # Attempt to fix common JSON issues
            try:
                # Remove invalid control characters
                json_string_clean = re.sub(r"[\x00-\x1F\x7F]", "", json_string)
                parsed_json = json.loads(json_string_clean)
                return parsed_json
            except json.JSONDecodeError:
                continue  # Try next match

    return None  # No valid JSON found


def create_client(model):
    if model.startswith("claude-"):
        print(f"Using Anthropic API with model {model}.")
        return anthropic.Anthropic(), model
    elif model.startswith("bedrock") and "claude" in model:
        client_model = model.split("/")[-1]
        print(f"Using Amazon Bedrock with model {client_model}.")
        return anthropic.AnthropicBedrock(), client_model
    elif model.startswith("vertex_ai") and "claude" in model:
        client_model = model.split("/")[-1]
        print(f"Using Vertex AI with model {client_model}.")
        return anthropic.AnthropicVertex(), client_model
    elif 'gpt' in model or "o1" in model or "o3" in model:
        print(f"Using OpenAI API with model {model}.")
        return openai.OpenAI(), model
    elif model in ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"]:
        print(f"Using OpenAI API with {model}.")
        return openai.OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com"
        ), model
    elif model == "llama3.1-405b":
        print(f"Using OpenAI API with {model}.")
        return openai.OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1"
        ), "meta-llama/llama-3.1-405b-instruct"
    elif "gemini" in model:
        print(f"Using OpenAI API with {model}.")
        return openai.OpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        ), model
    else:
        raise ValueError(f"Model {model} not supported.")
```

## File: llm_async.py

- Extension: .py
- Language: python
- Size: 1988 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
import os
from dotenv import load_dotenv
load_dotenv()

import asyncio
from openai import AsyncOpenAI
import openai
import backoff

# MAX_NUM_TOKENS = 4096

class GPT:
    def __init__(self, model, system_prompt, temperature=1.):
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    @backoff.on_exception(backoff.expo, (openai.RateLimitError, openai.APITimeoutError, openai.PermissionDeniedError))
    async def get_completion_async(self, prompt, n_responses=1):
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            # max_tokens=MAX_NUM_TOKENS,
            n=n_responses,
            stop=None,
            seed=0,
        )
        return [r.message.content for r in response.choices]

    async def get_multiple_completions_async(self, prompts, n_responses=1):
        results = await asyncio.gather(*(self.get_completion_async(p, n_responses) for p in prompts))
        return results
    
    def get_completion(self, prompt, n_responses=1):
        return asyncio.run(self.get_completion_async(prompt, n_responses))

    def get_multiple_completions(self, prompts, n_responses=1):
        return asyncio.run(self.get_multiple_completions_async(prompts, n_responses))
        
if __name__ == "__main__":
    gpt = GPT(model="gpt-4o-mini", system_prompt="You are a helpful assistant.")
    prompts = ["Hello", "Tell me a joke", "What's 2+2?", "What's the capital of France?"]

    for p in prompts:
        c = gpt.get_completion(p)
        print(c)

    results = gpt.get_multiple_completions(prompts, n_responses=2)
    print(results)
    

```

## File: llm_corewar.py

- Extension: .py
- Language: python
- Size: 3265 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
import re
import numpy as np
import hashlib

from dataclasses import dataclass
from corewar import redcode, Warrior

from llm_async import GPT

@dataclass
class GPTWarrior:
    prompt: str
    llm_response: str
    warrior: Warrior = None
    error: str = None
    id: str = None
    parent_id: str = None

    full_outputs: dict = None
    outputs: dict = None
    fitness: float = -np.inf
    bc: tuple[int, int] | None = None


class CorewarGPT():
    def __init__(self, model, system_prompt, new_warrior_prompt, mutate_warrior_prompt, temperature=1., environment=None):
        self.new_warrior_prompt = new_warrior_prompt
        self.mutate_warrior_prompt = mutate_warrior_prompt
        self.gpt = GPT(model=model, system_prompt=system_prompt, temperature=temperature)
        self.environment = environment
        self.all_generations = [] # list of tuples of (generation_type, gpt_warriors)

    def parse_llm_response(self, prompt, llm_response):
        gpt_warrior = GPTWarrior(prompt=prompt, llm_response=llm_response)
        try:
            # a = re.search(r"```.*\n[\s\S]*?```", warrior_str)
            llm_response = re.sub(r"```.*", "", llm_response) # remove the backticks and language tag
            warrior = redcode.parse(llm_response.split("\n"), self.environment)
            gpt_warrior.warrior = warrior
        except Exception as e:
            gpt_warrior.error = str(e)
        gpt_warrior.id = hashlib.sha256(gpt_warrior.llm_response.encode()).hexdigest()
        return gpt_warrior

    async def new_warrior_async(self, n_warriors=1, n_responses=1):
        prompts = [self.new_warrior_prompt for _ in range(n_warriors)]
        llm_responses = await self.gpt.get_multiple_completions_async(prompts, n_responses=n_responses) # list of list of strs
        gpt_warriors = [[None for _ in range(n_responses)] for _ in range(n_warriors)]
        for i_warrior in range(n_warriors):
            for i_response in range(n_responses):
                gpt_warrior = self.parse_llm_response(prompts[i_warrior], llm_responses[i_warrior][i_response])
                gpt_warriors[i_warrior][i_response] = gpt_warrior
        self.all_generations.append(("new_warrior", gpt_warriors))
        return np.array(gpt_warriors, dtype=object)
        
    async def mutate_warrior_async(self, gpt_warriors, n_responses=1):
        old_gpt_warriors = gpt_warriors
        prompts = [f"{self.mutate_warrior_prompt}\n\n\n{gpt_warrior.llm_response}" for gpt_warrior in old_gpt_warriors]
        llm_responses = await self.gpt.get_multiple_completions_async(prompts, n_responses=n_responses) # list of list of strs
        gpt_warriors = [[None for _ in range(n_responses)] for _ in range(len(llm_responses))]
        for i_warrior in range(len(llm_responses)):
            for i_response in range(n_responses):
                gpt_warrior = self.parse_llm_response(prompts[i_warrior], llm_responses[i_warrior][i_response])
                gpt_warrior.parent_id = old_gpt_warriors[i_warrior].id
                gpt_warriors[i_warrior][i_response] = gpt_warrior
        self.all_generations.append(("mutate_warrior", gpt_warriors))
        return np.array(gpt_warriors, dtype=object)

```

## File: util.py

- Extension: .py
- Language: python
- Size: 849 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
import os
import json
import pickle


def save_json(save_dir, name, item):
    if save_dir is not None:
        os.makedirs(f"{save_dir}/", exist_ok=True)
        with open(f"{save_dir}/{name}.json", "w") as f:
            json.dump(item, f)
            
def load_json(load_dir, name):
    if load_dir is not None:
        with open(f"{load_dir}/{name}.json", "r") as f:
            return json.load(f)
    else:
        return None

def save_pkl(save_dir, name, item):
    if save_dir is not None:
        os.makedirs(f"{save_dir}/", exist_ok=True)
        with open(f"{save_dir}/{name}.pkl", "wb") as f:
            pickle.dump(item, f)


def load_pkl(load_dir, name):
    if load_dir is not None:
        with open(f"{load_dir}/{name}.pkl", "rb") as f:
            return pickle.load(f)
    else:
        return None
```

## File: corewar\.travis.yml

- Extension: .yml
- Language: yaml
- Size: 40 bytes
- Created: 2026-01-14 15:04:49
- Modified: 2026-01-14 15:04:49

### Code

```yaml
language: python

script: ./tests.py

```

## File: corewar\graphics_random.py

- Extension: .py
- Language: python
- Size: 21113 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
#! /usr/bin/env python
# coding: utf-8

import pygame
from pygame.locals import *

from corewar.core import Core, DEFAULT_INITIAL_INSTRUCTION
from corewar.mars import *
from corewar.redcode import *
import os

INSTRUCTIONS_PER_LINE = 80
INSTRUCTION_SIZE_X = 9
INSTRUCTION_SIZE_Y = 9

ZOOM_VIEW_WIDTH = 200

I_SIZE = (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)
I_AREA = ((0,0), I_SIZE)

IMAGE_BG_COLOR = (255,255,254,255)
IMAGE_FG_COLOR = (0,0,1,255)

OPCODE_SURFACES = None

DEFAULT_BG_COLOR = (0, 0, 0)
DEFAULT_FG_COLOR = (60,60,60)
BLACK = (0, 0, 0)
WHITE = (255,255,255)

# Colors are dark and bright
WARRIOR_COLORS_ = (((0,0,100), (0,0,255)),
                  ((0,100,0), (0,255,0)),
                  ((0,100,100), (0,255,255)),
                  ((100,0,0), (255,0,0)),
                  ((100,0,100), (255,0,255)),
                  ((100,100,0), (255,255,0)))


WARRIOR_COLORS_ = (((127, 0, 0), (255, 0, 0)),
 ((127, 67, 0), (255, 135, 0)),
 ((127, 105, 0), (255, 211, 0)),
 ((111, 127, 5), (222, 255, 10)),
 ((80, 127, 5), (161, 255, 10)),
 ((5, 127, 76), (10, 255, 153)),
 ((5, 119, 127), (10, 239, 255)),
 ((10, 62, 122), (20, 125, 245)),
 ((44, 5, 127), (88, 10, 255)),
 ((95, 5, 127), (190, 10, 255)))

WARRIOR_COLORS_ = (((0, 9, 12), (0, 18, 25)),
 ((0, 47, 57), (0, 95, 115)),
 ((5, 73, 75), (10, 147, 150)),
 ((74, 105, 94), (148, 210, 189)),
 ((116, 108, 83), (233, 216, 166)),
 ((119, 77, 0), (238, 155, 0)),
 ((101, 51, 1), (202, 103, 2)),
 ((93, 31, 1), (187, 62, 3)),
 ((87, 16, 9), (174, 32, 18)),
 ((77, 17, 19), (155, 34, 38)))


WARRIOR_COLORS = (((124, 32, 34), (249, 65, 68)),
 ((121, 57, 22), (243, 114, 44)),
 ((124, 75, 15), (248, 150, 30)),
 ((124, 66, 37), (249, 132, 74)),
 ((124, 99, 39), (249, 199, 79)),
 ((72, 95, 54), (144, 190, 109)),
 ((33, 85, 69), (67, 170, 139)),
 ((38, 72, 71), (77, 144, 142)),
 ((43, 58, 72), (87, 117, 144)),
 ((19, 62, 80), (39, 125, 161)))


def load_opcode_surfaces():
    "Load the images of the opcodes from the file"
    all_instructions = pygame.image.load('pixels/instructions.png')
    class Y:
        y = -INSTRUCTION_SIZE_Y
        def __call__(self):
            self.y += INSTRUCTION_SIZE_Y
            return self.y
    y = Y()

    return {
        DAT: all_instructions.subsurface(((0,y()), I_SIZE)),
        MOV: all_instructions.subsurface(((0,y()), I_SIZE)),
        ADD: all_instructions.subsurface(((0,y()), I_SIZE)),
        SUB: all_instructions.subsurface(((0,y()), I_SIZE)),
        MUL: all_instructions.subsurface(((0,y()), I_SIZE)),
        DIV: all_instructions.subsurface(((0,y()), I_SIZE)),
        MOD: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMP: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMZ: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMN: all_instructions.subsurface(((0,y()), I_SIZE)),
        DJN: all_instructions.subsurface(((0,y()), I_SIZE)),
        SPL: all_instructions.subsurface(((0,y()), I_SIZE)),
        SLT: all_instructions.subsurface(((0,y()), I_SIZE)),
        CMP: all_instructions.subsurface(((0,y()), I_SIZE)),
        SEQ: all_instructions.subsurface(((0,y()), I_SIZE)),
        SNE: all_instructions.subsurface(((0,y()), I_SIZE)),
        NOP: all_instructions.subsurface(((0,y()), I_SIZE))}

def opcode_surface(opcode, foreground=None, background=None):
    "Return a surface representing an instruction in the core"
    surface = pygame.Surface(I_SIZE)
    opcode_surface = OPCODE_SURFACES[opcode].convert(surface)

    if background:
        surface.fill(background) # fill background color
        opcode_surface.set_colorkey(IMAGE_BG_COLOR) # make image bg transparent
        surface.blit(opcode_surface, (0,0)) # blit opcode in background
        surface.set_colorkey(IMAGE_FG_COLOR) # make image fg transparent

    if foreground:
        fg_surface = pygame.Surface(I_SIZE)
        fg_surface.fill(foreground) # fill foreground color
        opcode_surface.set_colorkey(IMAGE_FG_COLOR) # make image fg transparent
        fg_surface.blit(opcode_surface, (0,0)) # blit opcode in background
        fg_surface.set_colorkey(IMAGE_BG_COLOR) # make image bg transparent

        surface.blit(fg_surface, (0,0)) # blit in background

    return surface

class MyMARS(MARS):
    def __init__(self, core=None, warriors=None, minimum_separation=100, randomize=True, max_processes=None):
        self.core = core if core else Core()
        self.minimum_separation = minimum_separation
        self.max_processes = max_processes if max_processes else len(self.core)
        self.warriors = warriors if warriors else []
        self.warrior_cov = {w: np.zeros(len(self.core), dtype=bool) for w in self.warriors}
        # self.warrior_tsp = {w: 0 for w in self.warriors}  # total spawned processes

        if self.warriors:
            self.load_warriors(randomize)

    def core_event(self, warrior, address, event_type):
        i = self.core[address]
        assert isinstance(i.a_number, int), f"Expected int but got {type(i.a_number)}"
        assert isinstance(i.b_number, int), f"Expected int but got {type(i.b_number)}"
        i.a_number = min(max(i.a_number, -999999999), 999999999)
        i.b_number = min(max(i.b_number, -999999999), 999999999)
        assert i.a_number < 1000000000 and i.a_number > -1000000000, f"a_number out of bounds"
        assert i.b_number < 1000000000 and i.b_number > -1000000000, f"b_number out of bounds"
    
    def enqueue(self, warrior, address):
        """Enqueue another process into the warrior's task queue. Only if it's
           not already full.
        """
        if len(warrior.task_queue) < self.max_processes:
            warrior.task_queue.append(self.core.trim(address))
            # self.warrior_cov[warrior][self.core.trim(address)] = True
            # self.warrior_tsp[warrior] += 1

class PygameMARS(MyMARS):
    "A MARS with a surface drawing of the core"

    def __init__(self, *args, **kargs):
        super(PygameMARS, self).__init__(*args, **kargs)
        self.size = (INSTRUCTION_SIZE_X * INSTRUCTIONS_PER_LINE,
                     INSTRUCTION_SIZE_Y * (len(self) // INSTRUCTIONS_PER_LINE))
        self.core_surface = pygame.Surface(self.size)
        self.recent_events = pygame.Surface(self.size)
        self.recent_events.set_colorkey(DEFAULT_BG_COLOR)

    def reset(self, clear_instruction=DEFAULT_INITIAL_INSTRUCTION):
        self.core.clear(clear_instruction)
        for n, instruction in enumerate(self):
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  DEFAULT_FG_COLOR,
                                                  DEFAULT_BG_COLOR),
                                   ((n % INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_X,
                                    (n // INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_Y))
        self.load_warriors()

    def load_warriors(self):
        super(PygameMARS, self).load_warriors()
        for instruction in self:
            instruction.fg_color = DEFAULT_FG_COLOR
            instruction.bg_color = DEFAULT_BG_COLOR

    def step(self):
        self.recent_events.fill(DEFAULT_BG_COLOR)
        super(PygameMARS, self).step()

    def blit_into(self, surface, dest):
        surface.blit(self.core_surface, dest)
        surface.blit(self.recent_events, dest)

    def core_event(self, warrior, address, event_type):
        address %= len(self)
        position = ((address % INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_X,
                    (address // INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_Y)
        instruction = self.core[address]

        if event_type in (EVENT_I_WRITE, EVENT_A_WRITE, EVENT_B_WRITE):
            # In case of a write event, we write the foreground with the
            # warrior's color
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  warrior.color[1],
                                                  None),
                                   position, area=I_AREA)
            self.recent_events.blit(opcode_surface(instruction.opcode,
                                                   WHITE,
                                                   DEFAULT_BG_COLOR),
                                    position, area=I_AREA)
            instruction.fg_color = warrior.color[1]
        elif event_type == EVENT_EXECUTED:
            # In case of execution, we write the background with warrior's color
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  WHITE,
                                                  warrior.color[0]),
                                   position, area=I_AREA)
            self.recent_events.blit(opcode_surface(instruction.opcode,
                                                   BLACK,
                                                   warrior.color[1]),
                                    position, area=I_AREA)
            instruction.fg_color = WHITE
            instruction.bg_color = warrior.color[0]
        elif event_type in (EVENT_A_ARITH, EVENT_B_ARITH, EVENT_A_DEC,
                            EVENT_B_DEC, EVENT_A_INC, EVENT_B_INC):
            # In case of arithmetic modification, or increment/decrement, we
            # write a rectangle around the instruction
            pygame.draw.rect(self.core_surface, warrior.color[0],
                             (position, (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)),
                              1)
            pygame.draw.rect(self.recent_events, warrior.color[1],
                             (position, (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)),
                              1)


if __name__ == "__main__":
    # import argparse
    from dataclasses import dataclass
    import tyro
    import sys

    # parser = argparse.ArgumentParser(description='MARS (Memory Array Redcode Simulator)')
    # parser.add_argument('--rounds', '-r', metavar='ROUNDS', type=int, nargs='?',
    #                     default=1, help='Rounds to play')
    # parser.add_argument('--paused', action='store_true', default=False,
    #                     help='Start each round paused')
    # parser.add_argument('--size', '-s', metavar='CORESIZE', type=int, nargs='?',
    #                     default=8000, help='The core size')
    # parser.add_argument('--cycles', '-c', metavar='CYCLES', type=int, nargs='?',
    #                     default=80000, help='Cycles until tie')
    # parser.add_argument('--processes', '-p', metavar='MAXPROCESSES', type=int, nargs='?',
    #                     default=8000, help='Max processes')
    # parser.add_argument('--length', '-l', metavar='MAXLENGTH', type=int, nargs='?',
    #                     default=100, help='Max warrior length')
    # parser.add_argument('--distance', '-d', metavar='MINDISTANCE', type=int, nargs='?',
    #                     default=100, help='Minimum warrior distance')
    # parser.add_argument('warriors', metavar='WARRIOR', type=str, nargs='+',
    #                     help='Warrior redcode filename')
    @dataclass
    class Args:
        # warriors: list[str] # List of warrior redcode filenames
        rounds: int = 100 # Rounds to play
        paused: bool | None = False # Start each round paused
        size: int = 8000 # The core size
        cycles: int = 80000 # Cycles until tie
        processes: int = 8000 # Max processes
        length: int = 100 # Max warrior length
        distance: int = 100 # Minimum warrior distance
        seed: int = 0

        warrior_dir: str | None = None
        start_cycles: int = 0

    args = tyro.cli(Args)

    import numpy as np
    import random
    np.random.seed(args.seed)
    random.seed(args.seed)


    # if len(args.warriors) > len(WARRIOR_COLORS):
        # print("Please specify a maximum of {} warriors.".format(len(WARRIOR_COLORS)), file=sys.stderr)
        # sys.exit(1)

    # build environment
    environment = {'CORESIZE': args.size,
                   'CYCLES': args.cycles,
                   'ROUNDS': args.rounds,
                   'MAXPROCESSES': args.processes,
                   'MAXLENGTH': args.length,
                   'MINDISTANCE': args.distance}

    # assemble warriors
    # warriors = [parse(file, environment) for file in args.warriors]
    # warriors = []
    # for file in args.warriors:
    #     with open(file, encoding="utf-8", errors="replace") as f:
    #         warrior = parse(f.readlines(), environment)
    #         warriors.append(warrior)
    
    def load_warriors(warrior_files):
        warriors = []
        for file in warrior_files:
            with open(file, encoding="utf-8", errors="replace") as f:
                warrior = parse(f.readlines(), environment)
                warriors.append(warrior)
        return warriors
    
    warrior_files = [os.path.join(args.warrior_dir, wf) for wf in os.listdir(args.warrior_dir)]
    all_warriors = load_warriors(warrior_files)
    # warriors = all_warriors[100:106]
    warriors = np.random.choice(all_warriors, 6, replace=False)

    # raise ValueError

    # initialize wins, losses, ties and color for each warrior
    for warrior, color in zip(warriors, WARRIOR_COLORS):
        warrior.wins = warrior.ties = warrior.losses = 0
        warrior.color = color

    # create MARS
    simulation = PygameMARS(minimum_separation = args.distance,
                            max_processes = args.processes)
    simulation.warriors = warriors

    # initialize pygame engine
    pygame.init()

    # core instruction's font
    core_font = pygame.font.SysFont("monospace", 12)

    # Load surfaces from file
    OPCODE_SURFACES = load_opcode_surfaces()

    # create display
    display_surface = pygame.display.set_mode((simulation.size[0] + ZOOM_VIEW_WIDTH,
                                               simulation.size[1]))

    # initializations
    c_address = 0

    # control variables
    paused = False
    stop_rounds = False

    # create clock to control FPS
    clock = pygame.time.Clock()

    # for each round
    for round in range(1, args.rounds + 1):
        warriors = np.random.choice(all_warriors, 10, replace=False)
        for warrior, color in zip(warriors, WARRIOR_COLORS):
            warrior.wins = warrior.ties = warrior.losses = 0
            warrior.color = color
        simulation.warriors = warriors

        # reset simulation and load warriors
        simulation.reset()
        for _ in range(args.start_cycles):
            simulation.step()

        # start with all warriors active
        active_warriors = list(warriors)

        # how many warriors should be playing to skip to next round
        active_warrior_to_stop = 1 if len(warriors) >= 2 else 0

        # start paused if user requested from command line
        if args.paused:
            paused = True

        # control variable
        next_round = False

        print()
        print("Starting round {}".format(round))

        for cycle in range(args.cycles):
            # if cycle==1000:
            # if cycle > 0:
                # os.makedirs(f"videos/drq_random_{round:03d}", exist_ok=True)
                # pygame.image.save(display_surface, f"videos/drq_random_{round:03d}/frame_{cycle-1:05d}.png")
            #     print('DONEEEEEE')
            #     os.exit(0)
            # step one simulation in MARS
            simulation.step()

            # get mouse position
            mouse_pos = pygame.mouse.get_pos()
            # calculate address based on mouse position if position is over core
            if 0 <= mouse_pos[0] <= simulation.size[0] and 0 <= mouse_pos[1] <= simulation.size[1]:
                c_address = (INSTRUCTIONS_PER_LINE * (mouse_pos[1]//INSTRUCTION_SIZE_Y) +
                             (mouse_pos[0] // INSTRUCTION_SIZE_X))

            # clear display part of instructions
            display_surface.fill(BLACK, ((simulation.size[0], 0),
                                         (ZOOM_VIEW_WIDTH, simulation.size[1])))
            for n, address in enumerate(range(c_address-18, c_address+18)):
                instruction = simulation[address]
                i_surface = core_font.render("%04d %s" % (address,
                                                          instruction),
                                               True,
                                               instruction.fg_color)
                pygame.draw.rect(display_surface, instruction.bg_color,
                                 ((simulation.size[0], n*20),
                                  (simulation.size[0] + ZOOM_VIEW_WIDTH,
                                   (n+1)*20)))
                display_surface.blit(i_surface, (simulation.size[0], n*20))

            # blit MARS visualization into display
            simulation.blit_into(display_surface, (0,0))
            pygame.display.update()
            clock.tick(250)

            to_remove = []
            for warrior in active_warriors:
                if not warrior.task_queue:
                    print("{} ({}) losses after {} cycles.".format(warrior.name,
                                                                    warrior.author,
                                                                    cycle))
                    warrior.losses += 1
                    to_remove.append(warrior)

            for warrior in to_remove:
                active_warriors.remove(warrior)

            # if there's only one left, or are all dead, then stop simulation
            if len(active_warriors) <= active_warrior_to_stop:
                for warrior in active_warriors:
                    print("{} ({}) wins after {} cycles.".format(warrior.name,
                                                                  warrior.author,
                                                                  cycle))
                    warrior.wins += 1
                break

            step = False
            while True:
                for event in pygame.event.get():
                    if event.type == QUIT:
                        # Tie all remaining bots and go to final results
                        next_round = True
                        stop_rounds = True
                        paused = False
                    elif event.type == KEYDOWN:
                        if event.key == K_SPACE:
                            # toggle pausing
                            paused = not paused
                        elif event.key == K_s:
                            # step simulation (and pause)
                            paused = True
                            step = True
                        elif event.key == K_n:
                            # Tie all remaining bots and go to next round
                            next_round = True

                if not paused or step or next_round:
                    break

            if next_round:
                for warrior in active_warriors:
                    if warrior.task_queue:
                        print("{} ({}) ties after {} cycles.".format(warrior.name,
                                                                    warrior.author,
                                                                    cycle))
                        warrior.ties += 1
                break
        else:
            # running until max cycles: tie
            for warrior in active_warriors:
                if warrior.task_queue:
                    print("{} ({}) ties after {} cycles.".format(warrior.name,
                                                                  warrior.author,
                                                                  cycle))
                    warrior.ties += 1

        if stop_rounds:
            break

    # print final results
    print()
    print("Final results: ({} rounds)".format(round))
    print("{} {} {} {}".format("Warrior (Author)".ljust(40), "wins".rjust(5),
                              "ties".rjust(5), "losses".rjust(5)))
    for warrior in warriors:
        print("{} {} {} {}".format(("{} ({})".format(warrior.name, warrior.author)).ljust(40),
                                  str(warrior.wins).rjust(5),
                                  str(warrior.ties).rjust(5),
                                  str(warrior.losses).rjust(5)))

    if not stop_rounds and not next_round:
        # keeps display open, until quit
        paused = True
        while paused:
            for event in pygame.event.get():
                if event.type == QUIT:
                    paused = False

    # exit pygame
    pygame.quit()


```

## File: corewar\graphics_rounds.py

- Extension: .py
- Language: python
- Size: 21259 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
#! /usr/bin/env python
# coding: utf-8

import pygame
from pygame.locals import *

from corewar.core import Core, DEFAULT_INITIAL_INSTRUCTION
from corewar.mars import *
from corewar.redcode import *
import os

INSTRUCTIONS_PER_LINE = 80
INSTRUCTION_SIZE_X = 9
INSTRUCTION_SIZE_Y = 9

ZOOM_VIEW_WIDTH = 200

I_SIZE = (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)
I_AREA = ((0,0), I_SIZE)

IMAGE_BG_COLOR = (255,255,254,255)
IMAGE_FG_COLOR = (0,0,1,255)

OPCODE_SURFACES = None

DEFAULT_BG_COLOR = (0, 0, 0)
DEFAULT_FG_COLOR = (60,60,60)
BLACK = (0, 0, 0)
WHITE = (255,255,255)

# Colors are dark and bright
WARRIOR_COLORS_ = (((0,0,100), (0,0,255)),
                  ((0,100,0), (0,255,0)),
                  ((0,100,100), (0,255,255)),
                  ((100,0,0), (255,0,0)),
                  ((100,0,100), (255,0,255)),
                  ((100,100,0), (255,255,0)))


WARRIOR_COLORS_ = (((127, 0, 0), (255, 0, 0)),
 ((127, 67, 0), (255, 135, 0)),
 ((127, 105, 0), (255, 211, 0)),
 ((111, 127, 5), (222, 255, 10)),
 ((80, 127, 5), (161, 255, 10)),
 ((5, 127, 76), (10, 255, 153)),
 ((5, 119, 127), (10, 239, 255)),
 ((10, 62, 122), (20, 125, 245)),
 ((44, 5, 127), (88, 10, 255)),
 ((95, 5, 127), (190, 10, 255)))

WARRIOR_COLORS_ = (((0, 9, 12), (0, 18, 25)),
 ((0, 47, 57), (0, 95, 115)),
 ((5, 73, 75), (10, 147, 150)),
 ((74, 105, 94), (148, 210, 189)),
 ((116, 108, 83), (233, 216, 166)),
 ((119, 77, 0), (238, 155, 0)),
 ((101, 51, 1), (202, 103, 2)),
 ((93, 31, 1), (187, 62, 3)),
 ((87, 16, 9), (174, 32, 18)),
 ((77, 17, 19), (155, 34, 38)))


WARRIOR_COLORS = (((124, 32, 34), (249, 65, 68)),
 ((121, 57, 22), (243, 114, 44)),
 ((124, 75, 15), (248, 150, 30)),
 ((124, 66, 37), (249, 132, 74)),
 ((124, 99, 39), (249, 199, 79)),
 ((72, 95, 54), (144, 190, 109)),
 ((33, 85, 69), (67, 170, 139)),
 ((38, 72, 71), (77, 144, 142)),
 ((43, 58, 72), (87, 117, 144)),
 ((19, 62, 80), (39, 125, 161)))


def load_opcode_surfaces():
    "Load the images of the opcodes from the file"
    all_instructions = pygame.image.load('pixels/instructions.png')
    class Y:
        y = -INSTRUCTION_SIZE_Y
        def __call__(self):
            self.y += INSTRUCTION_SIZE_Y
            return self.y
    y = Y()

    return {
        DAT: all_instructions.subsurface(((0,y()), I_SIZE)),
        MOV: all_instructions.subsurface(((0,y()), I_SIZE)),
        ADD: all_instructions.subsurface(((0,y()), I_SIZE)),
        SUB: all_instructions.subsurface(((0,y()), I_SIZE)),
        MUL: all_instructions.subsurface(((0,y()), I_SIZE)),
        DIV: all_instructions.subsurface(((0,y()), I_SIZE)),
        MOD: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMP: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMZ: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMN: all_instructions.subsurface(((0,y()), I_SIZE)),
        DJN: all_instructions.subsurface(((0,y()), I_SIZE)),
        SPL: all_instructions.subsurface(((0,y()), I_SIZE)),
        SLT: all_instructions.subsurface(((0,y()), I_SIZE)),
        CMP: all_instructions.subsurface(((0,y()), I_SIZE)),
        SEQ: all_instructions.subsurface(((0,y()), I_SIZE)),
        SNE: all_instructions.subsurface(((0,y()), I_SIZE)),
        NOP: all_instructions.subsurface(((0,y()), I_SIZE))}

def opcode_surface(opcode, foreground=None, background=None):
    "Return a surface representing an instruction in the core"
    surface = pygame.Surface(I_SIZE)
    opcode_surface = OPCODE_SURFACES[opcode].convert(surface)

    if background:
        surface.fill(background) # fill background color
        opcode_surface.set_colorkey(IMAGE_BG_COLOR) # make image bg transparent
        surface.blit(opcode_surface, (0,0)) # blit opcode in background
        surface.set_colorkey(IMAGE_FG_COLOR) # make image fg transparent

    if foreground:
        fg_surface = pygame.Surface(I_SIZE)
        fg_surface.fill(foreground) # fill foreground color
        opcode_surface.set_colorkey(IMAGE_FG_COLOR) # make image fg transparent
        fg_surface.blit(opcode_surface, (0,0)) # blit opcode in background
        fg_surface.set_colorkey(IMAGE_BG_COLOR) # make image bg transparent

        surface.blit(fg_surface, (0,0)) # blit in background

    return surface

class MyMARS(MARS):
    def __init__(self, core=None, warriors=None, minimum_separation=100, randomize=True, max_processes=None):
        self.core = core if core else Core()
        self.minimum_separation = minimum_separation
        self.max_processes = max_processes if max_processes else len(self.core)
        self.warriors = warriors if warriors else []
        self.warrior_cov = {w: np.zeros(len(self.core), dtype=bool) for w in self.warriors}
        # self.warrior_tsp = {w: 0 for w in self.warriors}  # total spawned processes

        if self.warriors:
            self.load_warriors(randomize)

    def core_event(self, warrior, address, event_type):
        i = self.core[address]
        assert isinstance(i.a_number, int), f"Expected int but got {type(i.a_number)}"
        assert isinstance(i.b_number, int), f"Expected int but got {type(i.b_number)}"
        i.a_number = min(max(i.a_number, -999999999), 999999999)
        i.b_number = min(max(i.b_number, -999999999), 999999999)
        assert i.a_number < 1000000000 and i.a_number > -1000000000, f"a_number out of bounds"
        assert i.b_number < 1000000000 and i.b_number > -1000000000, f"b_number out of bounds"
    
    def enqueue(self, warrior, address):
        """Enqueue another process into the warrior's task queue. Only if it's
           not already full.
        """
        if len(warrior.task_queue) < self.max_processes:
            warrior.task_queue.append(self.core.trim(address))
            # self.warrior_cov[warrior][self.core.trim(address)] = True
            # self.warrior_tsp[warrior] += 1

class PygameMARS(MyMARS):
    "A MARS with a surface drawing of the core"

    def __init__(self, *args, **kargs):
        super(PygameMARS, self).__init__(*args, **kargs)
        self.size = (INSTRUCTION_SIZE_X * INSTRUCTIONS_PER_LINE,
                     INSTRUCTION_SIZE_Y * (len(self) // INSTRUCTIONS_PER_LINE))
        self.core_surface = pygame.Surface(self.size)
        self.recent_events = pygame.Surface(self.size)
        self.recent_events.set_colorkey(DEFAULT_BG_COLOR)

    def reset(self, clear_instruction=DEFAULT_INITIAL_INSTRUCTION):
        self.core.clear(clear_instruction)
        for n, instruction in enumerate(self):
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  DEFAULT_FG_COLOR,
                                                  DEFAULT_BG_COLOR),
                                   ((n % INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_X,
                                    (n // INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_Y))
        self.load_warriors()

    def load_warriors(self):
        super(PygameMARS, self).load_warriors()
        for instruction in self:
            instruction.fg_color = DEFAULT_FG_COLOR
            instruction.bg_color = DEFAULT_BG_COLOR

    def step(self):
        self.recent_events.fill(DEFAULT_BG_COLOR)
        super(PygameMARS, self).step()

    def blit_into(self, surface, dest):
        surface.blit(self.core_surface, dest)
        surface.blit(self.recent_events, dest)

    def core_event(self, warrior, address, event_type):
        address %= len(self)
        position = ((address % INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_X,
                    (address // INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_Y)
        instruction = self.core[address]

        if event_type in (EVENT_I_WRITE, EVENT_A_WRITE, EVENT_B_WRITE):
            # In case of a write event, we write the foreground with the
            # warrior's color
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  warrior.color[1],
                                                  None),
                                   position, area=I_AREA)
            self.recent_events.blit(opcode_surface(instruction.opcode,
                                                   WHITE,
                                                   DEFAULT_BG_COLOR),
                                    position, area=I_AREA)
            instruction.fg_color = warrior.color[1]
        elif event_type == EVENT_EXECUTED:
            # In case of execution, we write the background with warrior's color
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  WHITE,
                                                  warrior.color[0]),
                                   position, area=I_AREA)
            self.recent_events.blit(opcode_surface(instruction.opcode,
                                                   BLACK,
                                                   warrior.color[1]),
                                    position, area=I_AREA)
            instruction.fg_color = WHITE
            instruction.bg_color = warrior.color[0]
        elif event_type in (EVENT_A_ARITH, EVENT_B_ARITH, EVENT_A_DEC,
                            EVENT_B_DEC, EVENT_A_INC, EVENT_B_INC):
            # In case of arithmetic modification, or increment/decrement, we
            # write a rectangle around the instruction
            pygame.draw.rect(self.core_surface, warrior.color[0],
                             (position, (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)),
                              1)
            pygame.draw.rect(self.recent_events, warrior.color[1],
                             (position, (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)),
                              1)


if __name__ == "__main__":
    # import argparse
    from dataclasses import dataclass
    import tyro
    import sys

    # parser = argparse.ArgumentParser(description='MARS (Memory Array Redcode Simulator)')
    # parser.add_argument('--rounds', '-r', metavar='ROUNDS', type=int, nargs='?',
    #                     default=1, help='Rounds to play')
    # parser.add_argument('--paused', action='store_true', default=False,
    #                     help='Start each round paused')
    # parser.add_argument('--size', '-s', metavar='CORESIZE', type=int, nargs='?',
    #                     default=8000, help='The core size')
    # parser.add_argument('--cycles', '-c', metavar='CYCLES', type=int, nargs='?',
    #                     default=80000, help='Cycles until tie')
    # parser.add_argument('--processes', '-p', metavar='MAXPROCESSES', type=int, nargs='?',
    #                     default=8000, help='Max processes')
    # parser.add_argument('--length', '-l', metavar='MAXLENGTH', type=int, nargs='?',
    #                     default=100, help='Max warrior length')
    # parser.add_argument('--distance', '-d', metavar='MINDISTANCE', type=int, nargs='?',
    #                     default=100, help='Minimum warrior distance')
    # parser.add_argument('warriors', metavar='WARRIOR', type=str, nargs='+',
    #                     help='Warrior redcode filename')
    @dataclass
    class Args:
        # warriors: list[str] # List of warrior redcode filenames
        rounds: int = 100 # Rounds to play
        paused: bool | None = False # Start each round paused
        size: int = 8000 # The core size
        cycles: int = 80000 # Cycles until tie
        processes: int = 8000 # Max processes
        length: int = 100 # Max warrior length
        distance: int = 100 # Minimum warrior distance
        seed: int = 0

        warrior_dir: str | None = None
        start_cycles: int = 0
        target_round: int | None = None

    args = tyro.cli(Args)

    import numpy as np
    import random
    np.random.seed(args.seed)
    random.seed(args.seed)


    # if len(args.warriors) > len(WARRIOR_COLORS):
        # print("Please specify a maximum of {} warriors.".format(len(WARRIOR_COLORS)), file=sys.stderr)
        # sys.exit(1)

    # build environment
    environment = {'CORESIZE': args.size,
                   'CYCLES': args.cycles,
                   'ROUNDS': args.rounds,
                   'MAXPROCESSES': args.processes,
                   'MAXLENGTH': args.length,
                   'MINDISTANCE': args.distance}

    # assemble warriors
    # warriors = [parse(file, environment) for file in args.warriors]
    # warriors = []
    # for file in args.warriors:
    #     with open(file, encoding="utf-8", errors="replace") as f:
    #         warrior = parse(f.readlines(), environment)
    #         warriors.append(warrior)
    
    def load_warriors(warrior_files):
        warriors = []
        for file in warrior_files:
            with open(file, encoding="utf-8", errors="replace") as f:
                warrior = parse(f.readlines(), environment)
                warriors.append(warrior)
        return warriors
    
    # warrior_files = [os.path.join(args.warrior_dir, wf) for wf in os.listdir(args.warrior_dir)]
    import glob
    warrior_files = sorted(glob.glob(f"{args.warrior_dir}/drq_{args.target_round:03d}_*.red"))
    all_warriors = load_warriors(warrior_files)
    # warriors = all_warriors[100:106]
    # warriors = np.random.choice(all_warriors, 6, replace=False)
    warriors = all_warriors[:2]

    # raise ValueError

    # initialize wins, losses, ties and color for each warrior
    for warrior, color in zip(warriors, WARRIOR_COLORS):
        warrior.wins = warrior.ties = warrior.losses = 0
        warrior.color = color

    # create MARS
    simulation = PygameMARS(minimum_separation = args.distance,
                            max_processes = args.processes)
    simulation.warriors = warriors

    # initialize pygame engine
    pygame.init()

    # core instruction's font
    core_font = pygame.font.SysFont("monospace", 12)

    # Load surfaces from file
    OPCODE_SURFACES = load_opcode_surfaces()

    # create display
    display_surface = pygame.display.set_mode((simulation.size[0] + ZOOM_VIEW_WIDTH,
                                               simulation.size[1]))

    # initializations
    c_address = 0

    # control variables
    paused = False
    stop_rounds = False

    # create clock to control FPS
    clock = pygame.time.Clock()

    # for each round
    for round in range(1, args.rounds + 1):
        # warriors = np.random.choice(all_warriors, 10, replace=False)
        warriors = all_warriors[:1+round][-10:]
        for warrior, color in zip(warriors, WARRIOR_COLORS):
            warrior.wins = warrior.ties = warrior.losses = 0
            warrior.color = color
        simulation.warriors = warriors

        # reset simulation and load warriors
        simulation.reset()
        for _ in range(args.start_cycles):
            simulation.step()

        # start with all warriors active
        active_warriors = list(warriors)

        # how many warriors should be playing to skip to next round
        active_warrior_to_stop = 1 if len(warriors) >= 2 else 0

        # start paused if user requested from command line
        if args.paused:
            paused = True

        # control variable
        next_round = False

        print()
        print("Starting round {}".format(round))

        for cycle in range(args.cycles):
            # if cycle > 0:
            #     os.makedirs(f"videos/drq_random_{round:03d}", exist_ok=True)
            #     pygame.image.save(display_surface, f"videos/drq_random_{round:03d}/frame_{cycle-1:05d}.png")

            # step one simulation in MARS
            simulation.step()

            # get mouse position
            mouse_pos = pygame.mouse.get_pos()
            # calculate address based on mouse position if position is over core
            if 0 <= mouse_pos[0] <= simulation.size[0] and 0 <= mouse_pos[1] <= simulation.size[1]:
                c_address = (INSTRUCTIONS_PER_LINE * (mouse_pos[1]//INSTRUCTION_SIZE_Y) +
                             (mouse_pos[0] // INSTRUCTION_SIZE_X))

            # clear display part of instructions
            display_surface.fill(BLACK, ((simulation.size[0], 0),
                                         (ZOOM_VIEW_WIDTH, simulation.size[1])))
            for n, address in enumerate(range(c_address-18, c_address+18)):
                instruction = simulation[address]
                i_surface = core_font.render("%04d %s" % (address,
                                                          instruction),
                                               True,
                                               instruction.fg_color)
                pygame.draw.rect(display_surface, instruction.bg_color,
                                 ((simulation.size[0], n*20),
                                  (simulation.size[0] + ZOOM_VIEW_WIDTH,
                                   (n+1)*20)))
                display_surface.blit(i_surface, (simulation.size[0], n*20))

            # blit MARS visualization into display
            simulation.blit_into(display_surface, (0,0))
            pygame.display.update()
            clock.tick(1000)

            to_remove = []
            for warrior in active_warriors:
                if not warrior.task_queue:
                    print("{} ({}) losses after {} cycles.".format(warrior.name,
                                                                    warrior.author,
                                                                    cycle))
                    warrior.losses += 1
                    to_remove.append(warrior)

            for warrior in to_remove:
                active_warriors.remove(warrior)

            # if there's only one left, or are all dead, then stop simulation
            if len(active_warriors) <= active_warrior_to_stop:
                for warrior in active_warriors:
                    print("{} ({}) wins after {} cycles.".format(warrior.name,
                                                                  warrior.author,
                                                                  cycle))
                    warrior.wins += 1
                break

            step = False
            while True:
                for event in pygame.event.get():
                    if event.type == QUIT:
                        # Tie all remaining bots and go to final results
                        next_round = True
                        stop_rounds = True
                        paused = False
                    elif event.type == KEYDOWN:
                        if event.key == K_SPACE:
                            # toggle pausing
                            paused = not paused
                        elif event.key == K_s:
                            # step simulation (and pause)
                            paused = True
                            step = True
                        elif event.key == K_n:
                            # Tie all remaining bots and go to next round
                            next_round = True

                if not paused or step or next_round:
                    break

            if next_round:
                for warrior in active_warriors:
                    if warrior.task_queue:
                        print("{} ({}) ties after {} cycles.".format(warrior.name,
                                                                    warrior.author,
                                                                    cycle))
                        warrior.ties += 1
                break
        else:
            # running until max cycles: tie
            for warrior in active_warriors:
                if warrior.task_queue:
                    print("{} ({}) ties after {} cycles.".format(warrior.name,
                                                                  warrior.author,
                                                                  cycle))
                    warrior.ties += 1

        if stop_rounds:
            break

    # print final results
    print()
    print("Final results: ({} rounds)".format(round))
    print("{} {} {} {}".format("Warrior (Author)".ljust(40), "wins".rjust(5),
                              "ties".rjust(5), "losses".rjust(5)))
    for warrior in warriors:
        print("{} {} {} {}".format(("{} ({})".format(warrior.name, warrior.author)).ljust(40),
                                  str(warrior.wins).rjust(5),
                                  str(warrior.ties).rjust(5),
                                  str(warrior.losses).rjust(5)))

    if not stop_rounds and not next_round:
        # keeps display open, until quit
        paused = True
        while paused:
            for event in pygame.event.get():
                if event.type == QUIT:
                    paused = False

    # exit pygame
    pygame.quit()


```

## File: corewar\LICENSE

- Extension: 
- Language: unknown
- Size: 369 bytes
- Created: 2026-01-14 15:04:49
- Modified: 2026-01-14 15:04:49

### Code

```unknown
Copyright Rodrigo Setti 2013

The code included in this repository is licensed under a
Attribution-NonCommercial-ShareAlike 3.0 license, meaning that you are free to
copy, distribute, transmit and adapt this work for non-commercial use, but that
you must credit Rodrigo Setti as the original authors of the piece, and provide
a link to the original source code.

```

## File: corewar\llm_evolve.py

- Extension: .py
- Language: python
- Size: 3333 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
import os, sys
sys.path.append(os.path.abspath("corewar"))


import redcode
from core import Core
from mars import MARS

from tqdm.auto import tqdm
import matplotlib.pyplot as plt
import numpy as np

import tyro
from dataclasses import dataclass
import random
from functools import partial

from multiprocessing import Pool

@dataclass
class Args:
    warriors: list[str] # List of warrior redcode filenames
    rounds: int = 1 # Rounds to play
    paused: bool | None = False # Start each round paused
    size: int = 8000 # The core size
    cycles: int = 80000 # Cycles until tie
    processes: int = 8000 # Max processes
    length: int = 100 # Max warrior length
    distance: int = 100 # Minimum warrior distance

    gpt_warrior: str | None = None
    save_dir: str | None = None

def run_single_round(args, warriors, seed):
    random.seed(seed)
    simulation = MARS(warriors=warriors, minimum_separation=args.distance, max_processes=args.processes, randomize=True)
    scores = np.zeros(len(warriors))
    for t in range(args.cycles):
        simulation.step()

        alive_flags = np.array([len(warrior.task_queue)>0 for warrior in simulation.warriors]).astype(int)
        n_alive = sum(alive_flags)
        if n_alive==0:
            break
        scores += (alive_flags * (1./n_alive))
    return scores

def run_multiple_rounds(args, warriors, n_processes=16):
    run_single_round_fn = partial(run_single_round, args, warriors)
    seeds = list(range(args.rounds))
    with Pool(processes=n_processes) as pool:
        scores = pool.map(run_single_round_fn, seeds)
    scores = np.array(scores)
    return scores


import pickle
def save_pkl(save_dir, name, item):
    if save_dir is not None:
        os.makedirs(f"{save_dir}/", exist_ok=True)
        with open(f"{save_dir}/{name}.pkl", "wb") as f:
            pickle.dump(item, f)


def load_pkl(load_dir, name):
    if load_dir is not None:
        with open(f"{load_dir}/{name}.pkl", "rb") as f:
            return pickle.load(f)
    else:
        return None

def main(args):
    environment = {'ROUNDS': args.rounds,
                'CORESIZE': args.size,
                'CYCLES': args.cycles,
                'MAXPROCESSES': args.processes,
                'MAXLENGTH': args.length,
                'MINDISTANCE': args.distance}

    warriors = []
    for file in args.warriors:
        with open(file, encoding="utf-8", errors="replace") as f:
            a = f.readlines()
        warrior = redcode.parse(a, environment)
        warriors.append(warrior)
    
    if args.gpt_warrior is not None:
        gpt_warrior = load_pkl("warriors", args.gpt_warrior)
        print(gpt_warrior)
        warriors.append(gpt_warrior)
    
    scores = run_multiple_rounds(args, warriors, n_processes=16)
    print(scores.shape, scores.mean())

    if args.save_dir is not None:
        os.makedirs(args.save_dir, exist_ok=True)
        save_pkl(args.save_dir, "scores", scores)

if __name__ == "__main__":
    args = tyro.cli(Args)
    # args = Args(warriors=[f"warriors/{file}" for file in os.listdir("warriors")])
    # args = Args(warriors=["warriors/validate.red", "warriors/validate.red", "warriors/validate.red", "warriors/validate.red"])

    main(args)


```

## File: corewar\pyproject.toml

- Extension: .toml
- Language: toml
- Size: 491 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```toml
[project]
name = "corewar"
version = "0.1.0"
description = "A Core War simulator in Python"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}

authors = [
  {name = "Akarsh Kumar", email = "you@example.com"}
]

dependencies = [
  # Add any runtime deps here, e.g.:
  # "numpy >=1.20"
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["corewar"]
include-package-data = true

```

## File: corewar\README.md

- Extension: .md
- Language: markdown
- Size: 2597 bytes
- Created: 2026-01-14 15:04:49
- Modified: 2026-01-14 15:04:49

### Code

```markdown

# Core War

[![Build Status](https://travis-ci.org/rodrigosetti/corewar.svg?branch=master)](https://travis-ci.org/rodrigosetti/corewar)

The Canadian mathematician A. K. Dewdney (author of "The Planiverse") first
introduced Core War in a series of Scientific American articles
starting in 1984.

> Core War was inspired by a story I heard some years ago about a mischievous
> programmer at a large corporate research laboratory I shall designate X. The
> programmer wrote an assembly-language program called Creeper that would
> duplicate itself every time it was run. It could also spread from one
> computer to another in the network of the X corporation. The program had no
> function other than to perpetuate itself. Before long there were so many
> copies of Creeper that more useful programs and data were being crowded out.
> The growing infestation was not brought under control until someone thought
> of fighting fire with fire. A second self-duplicating program called Reaper
> was written.  Its purpose was to destroy copies of Creeper until it could
> find no more and then to destroy itself. Reaper did its job, and things were
> soon back to normal at the X lab.

In this game, computer programs (called "Warriors") compete in a virtual arena
for digital supremacy. Warriors are written in an Assembly dialect called
"Redcode".

[Wikipedia article](http://en.wikipedia.org/wiki/Core_War)

This is a Python implementation of the MARS (Memory Array Redcode Simulator).

    usage: graphics.py [-h] [--rounds [ROUNDS]] [--paused] [--size [CORESIZE]]
                       [--cycles [CYCLES]] [--processes [MAXPROCESSES]]
                       [--length [MAXLENGTH]] [--distance [MINDISTANCE]]
                       WARRIOR [WARRIOR ...]

    MARS (Memory Array Redcode Simulator)

    positional arguments:
      WARRIOR               Warrior redcode filename

    optional arguments:
      -h, --help            show this help message and exit
      --rounds [ROUNDS], -r [ROUNDS]
                            Rounds to play
      --paused              Start each round paused
      --size [CORESIZE], -s [CORESIZE]
                            The core size
      --cycles [CYCLES], -c [CYCLES]
                            Cycles until tie
      --processes [MAXPROCESSES], -p [MAXPROCESSES]
                            Max processes
      --length [MAXLENGTH], -l [MAXLENGTH]
                            Max warrior length
      --distance [MINDISTANCE], -d [MINDISTANCE]
                            Minimum warrior distance

```

## File: corewar\tests.py

- Extension: .py
- Language: python
- Size: 206 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
#! /usr/bin/env python
# coding: utf-8

import unittest

from tests.redcode_test import TestRedcodeAssembler
from tests.mars_test import TestMars

if __name__ == '__main__':
    unittest.main()


```

## File: corewar\corewar\core.py

- Extension: .py
- Language: python
- Size: 2379 bytes
- Created: 2026-01-14 15:04:49
- Modified: 2026-01-14 15:04:49

### Code

```python
# coding: utf-8

from copy import copy
from .redcode import Instruction

__all__ = ['DEFAULT_INITIAL_INSTRUCTION', 'Core']

DEFAULT_INITIAL_INSTRUCTION = Instruction('DAT', 'F', '$', 0, '$', 0)

class Core(object):
    """The Core itself. An array-like object with a bunch of instructions and
       warriors, and tasks.
    """

    def __init__(self, initial_instruction=DEFAULT_INITIAL_INSTRUCTION,
                 size=8000, read_limit=None, write_limit=None):
        self.size = size
        self.write_limit = write_limit if write_limit else self.size
        self.read_limit = read_limit if read_limit else self.size
        self.clear()

    def clear(self, instruction=DEFAULT_INITIAL_INSTRUCTION):
        """Writes the same instruction thorough the entire core.
        """
        self.instructions = [instruction.core_binded(self) for i in range(self.size)]

    def trim_write(self, address):
        "Return the trimmed address to write, considering the write limit."
        return self._trim(address, self.write_limit)

    def trim_read(self, address):
        "Return the trimmed address to read, considering the read limit."
        return self._trim(address, self.read_limit)

    def trim(self, value):
        "Return a trimmed value to the bounds of the core size"
        return value % len(self)

    def trim_signed(self, value):
        "Return a trimmed value to the bounds of -core size to +core size"
        return value % len(self) if abs(value) > len(self) else value

    def _trim(self, address, limit):
        "Trims an address in the core, given a limit."
        result = address % limit
        if result > limit//2:
            result += self.size - limit
        return result

    def __getitem__(self, address):
        return self.instructions[address % self.size]

    def __getslice__(self, start, stop):
        if start > stop:
            return self.instructions[start:] + self.instructions[:stop]
        else:
            return self.instructions[start:stop]

    def __setitem__(self, address, instruction):
        self.instructions[address % self.size] = instruction

    def __iter__(self):
        return iter(self.instructions)

    def __len__(self):
        return self.size

    def __repr__(self):
        return "<Core size=%d>" % self.size


```

## File: corewar\corewar\graphics.py

- Extension: .py
- Language: python
- Size: 16900 bytes
- Created: 2026-01-14 15:04:49
- Modified: 2026-01-14 15:04:49

### Code

```python
#! /usr/bin/env python
# coding: utf-8

import pygame
from pygame.locals import *

from core import DEFAULT_INITIAL_INSTRUCTION
from mars import *
from redcode import *

INSTRUCTIONS_PER_LINE = 100
INSTRUCTION_SIZE_X = 9
INSTRUCTION_SIZE_Y = 9

ZOOM_VIEW_WIDTH = 200

I_SIZE = (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)
I_AREA = ((0,0), I_SIZE)

IMAGE_BG_COLOR = (255,255,254,255)
IMAGE_FG_COLOR = (0,0,1,255)

OPCODE_SURFACES = None

DEFAULT_BG_COLOR = (0, 0, 0)
DEFAULT_FG_COLOR = (60,60,60)
BLACK = (0, 0, 0)
WHITE = (255,255,255)

# Colors are dark and bright
WARRIOR_COLORS = (((0,0,100), (0,0,255)),
                  ((0,100,0), (0,255,0)),
                  ((0,100,100), (0,255,255)),
                  ((100,0,0), (255,0,0)),
                  ((100,0,100), (255,0,255)),
                  ((100,100,0), (255,255,0)))

def load_opcode_surfaces():
    "Load the images of the opcodes from the file"
    all_instructions = pygame.image.load('pixels/instructions.png')
    class Y:
        y = -INSTRUCTION_SIZE_Y
        def __call__(self):
            self.y += INSTRUCTION_SIZE_Y
            return self.y
    y = Y()

    return {
        DAT: all_instructions.subsurface(((0,y()), I_SIZE)),
        MOV: all_instructions.subsurface(((0,y()), I_SIZE)),
        ADD: all_instructions.subsurface(((0,y()), I_SIZE)),
        SUB: all_instructions.subsurface(((0,y()), I_SIZE)),
        MUL: all_instructions.subsurface(((0,y()), I_SIZE)),
        DIV: all_instructions.subsurface(((0,y()), I_SIZE)),
        MOD: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMP: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMZ: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMN: all_instructions.subsurface(((0,y()), I_SIZE)),
        DJN: all_instructions.subsurface(((0,y()), I_SIZE)),
        SPL: all_instructions.subsurface(((0,y()), I_SIZE)),
        SLT: all_instructions.subsurface(((0,y()), I_SIZE)),
        CMP: all_instructions.subsurface(((0,y()), I_SIZE)),
        SEQ: all_instructions.subsurface(((0,y()), I_SIZE)),
        SNE: all_instructions.subsurface(((0,y()), I_SIZE)),
        NOP: all_instructions.subsurface(((0,y()), I_SIZE))}

def opcode_surface(opcode, foreground=None, background=None):
    "Return a surface representing an instruction in the core"
    surface = pygame.Surface(I_SIZE)
    opcode_surface = OPCODE_SURFACES[opcode].convert(surface)

    if background:
        surface.fill(background) # fill background color
        opcode_surface.set_colorkey(IMAGE_BG_COLOR) # make image bg transparent
        surface.blit(opcode_surface, (0,0)) # blit opcode in background
        surface.set_colorkey(IMAGE_FG_COLOR) # make image fg transparent

    if foreground:
        fg_surface = pygame.Surface(I_SIZE)
        fg_surface.fill(foreground) # fill foreground color
        opcode_surface.set_colorkey(IMAGE_FG_COLOR) # make image fg transparent
        fg_surface.blit(opcode_surface, (0,0)) # blit opcode in background
        fg_surface.set_colorkey(IMAGE_BG_COLOR) # make image bg transparent

        surface.blit(fg_surface, (0,0)) # blit in background

    return surface

class PygameMARS(MARS):
    "A MARS with a surface drawing of the core"

    def __init__(self, *args, **kargs):
        super(PygameMARS, self).__init__(*args, **kargs)
        self.size = (INSTRUCTION_SIZE_X * INSTRUCTIONS_PER_LINE,
                     INSTRUCTION_SIZE_Y * (len(self) // INSTRUCTIONS_PER_LINE))
        self.core_surface = pygame.Surface(self.size)
        self.recent_events = pygame.Surface(self.size)
        self.recent_events.set_colorkey(DEFAULT_BG_COLOR)

    def reset(self, clear_instruction=DEFAULT_INITIAL_INSTRUCTION):
        self.core.clear(clear_instruction)
        for n, instruction in enumerate(self):
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  DEFAULT_FG_COLOR,
                                                  DEFAULT_BG_COLOR),
                                   ((n % INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_X,
                                    (n // INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_Y))
        self.load_warriors()

    def load_warriors(self):
        super(PygameMARS, self).load_warriors()
        for instruction in self:
            instruction.fg_color = DEFAULT_FG_COLOR
            instruction.bg_color = DEFAULT_BG_COLOR

    def step(self):
        self.recent_events.fill(DEFAULT_BG_COLOR)
        super(PygameMARS, self).step()

    def blit_into(self, surface, dest):
        surface.blit(self.core_surface, dest)
        surface.blit(self.recent_events, dest)

    def core_event(self, warrior, address, event_type):
        address %= len(self)
        position = ((address % INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_X,
                    (address // INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_Y)
        instruction = self.core[address]

        if event_type in (EVENT_I_WRITE, EVENT_A_WRITE, EVENT_B_WRITE):
            # In case of a write event, we write the foreground with the
            # warrior's color
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  warrior.color[1],
                                                  None),
                                   position, area=I_AREA)
            self.recent_events.blit(opcode_surface(instruction.opcode,
                                                   WHITE,
                                                   DEFAULT_BG_COLOR),
                                    position, area=I_AREA)
            instruction.fg_color = warrior.color[1]
        elif event_type == EVENT_EXECUTED:
            # In case of execution, we write the background with warrior's color
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  WHITE,
                                                  warrior.color[0]),
                                   position, area=I_AREA)
            self.recent_events.blit(opcode_surface(instruction.opcode,
                                                   BLACK,
                                                   warrior.color[1]),
                                    position, area=I_AREA)
            instruction.fg_color = WHITE
            instruction.bg_color = warrior.color[0]
        elif event_type in (EVENT_A_ARITH, EVENT_B_ARITH, EVENT_A_DEC,
                            EVENT_B_DEC, EVENT_A_INC, EVENT_B_INC):
            # In case of arithmetic modification, or increment/decrement, we
            # write a rectangle around the instruction
            pygame.draw.rect(self.core_surface, warrior.color[0],
                             (position, (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)),
                              1)
            pygame.draw.rect(self.recent_events, warrior.color[1],
                             (position, (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)),
                              1)


if __name__ == "__main__":
    # import argparse
    from dataclasses import dataclass
    import tyro
    import sys

    # parser = argparse.ArgumentParser(description='MARS (Memory Array Redcode Simulator)')
    # parser.add_argument('--rounds', '-r', metavar='ROUNDS', type=int, nargs='?',
    #                     default=1, help='Rounds to play')
    # parser.add_argument('--paused', action='store_true', default=False,
    #                     help='Start each round paused')
    # parser.add_argument('--size', '-s', metavar='CORESIZE', type=int, nargs='?',
    #                     default=8000, help='The core size')
    # parser.add_argument('--cycles', '-c', metavar='CYCLES', type=int, nargs='?',
    #                     default=80000, help='Cycles until tie')
    # parser.add_argument('--processes', '-p', metavar='MAXPROCESSES', type=int, nargs='?',
    #                     default=8000, help='Max processes')
    # parser.add_argument('--length', '-l', metavar='MAXLENGTH', type=int, nargs='?',
    #                     default=100, help='Max warrior length')
    # parser.add_argument('--distance', '-d', metavar='MINDISTANCE', type=int, nargs='?',
    #                     default=100, help='Minimum warrior distance')
    # parser.add_argument('warriors', metavar='WARRIOR', type=str, nargs='+',
    #                     help='Warrior redcode filename')
    @dataclass
    class Args:
        warriors: list[str] # List of warrior redcode filenames
        rounds: int = 1 # Rounds to play
        paused: bool | None = False # Start each round paused
        size: int = 8000 # The core size
        cycles: int = 80000 # Cycles until tie
        processes: int = 8000 # Max processes
        length: int = 100 # Max warrior length
        distance: int = 100 # Minimum warrior distance

    args = tyro.cli(Args)


    if len(args.warriors) > len(WARRIOR_COLORS):
        print("Please specify a maximum of {} warriors.".format(len(WARRIOR_COLORS)), file=sys.stderr)
        sys.exit(1)

    # build environment
    environment = {'CORESIZE': args.size,
                   'CYCLES': args.cycles,
                   'ROUNDS': args.rounds,
                   'MAXPROCESSES': args.processes,
                   'MAXLENGTH': args.length,
                   'MINDISTANCE': args.distance}

    # assemble warriors
    # warriors = [parse(file, environment) for file in args.warriors]
    warriors = []
    for file in args.warriors:
        with open(file, encoding="utf-8", errors="replace") as f:
            warrior = parse(f.readlines(), environment)
            warriors.append(warrior)

    # initialize wins, losses, ties and color for each warrior
    for warrior, color in zip(warriors, WARRIOR_COLORS):
        warrior.wins = warrior.ties = warrior.losses = 0
        warrior.color = color

    # create MARS
    simulation = PygameMARS(minimum_separation = args.distance,
                            max_processes = args.processes)
    simulation.warriors = warriors

    # initialize pygame engine
    pygame.init()

    # core instruction's font
    core_font = pygame.font.SysFont("monospace", 12)

    # Load surfaces from file
    OPCODE_SURFACES = load_opcode_surfaces()

    # create display
    display_surface = pygame.display.set_mode((simulation.size[0] + ZOOM_VIEW_WIDTH,
                                               simulation.size[1]))

    # initializations
    c_address = 0

    # control variables
    paused = False
    stop_rounds = False

    # create clock to control FPS
    clock = pygame.time.Clock()

    # for each round
    for round in range(1, args.rounds + 1):

        # reset simulation and load warriors
        simulation.reset()

        # start with all warriors active
        active_warriors = list(warriors)

        # how many warriors should be playing to skip to next round
        active_warrior_to_stop = 1 if len(warriors) >= 2 else 0

        # start paused if user requested from command line
        if args.paused:
            paused = True

        # control variable
        next_round = False

        print()
        print("Starting round {}".format(round))

        for cycle in range(args.cycles):
            # step one simulation in MARS
            simulation.step()

            # get mouse position
            mouse_pos = pygame.mouse.get_pos()
            # calculate address based on mouse position if position is over core
            if 0 <= mouse_pos[0] <= simulation.size[0] and 0 <= mouse_pos[1] <= simulation.size[1]:
                c_address = (INSTRUCTIONS_PER_LINE * (mouse_pos[1]//INSTRUCTION_SIZE_Y) +
                             (mouse_pos[0] // INSTRUCTION_SIZE_X))

            # clear display part of instructions
            display_surface.fill(BLACK, ((simulation.size[0], 0),
                                         (ZOOM_VIEW_WIDTH, simulation.size[1])))
            for n, address in enumerate(range(c_address-18, c_address+18)):
                instruction = simulation[address]
                i_surface = core_font.render("%04d %s" % (address,
                                                          instruction),
                                               True,
                                               instruction.fg_color)
                pygame.draw.rect(display_surface, instruction.bg_color,
                                 ((simulation.size[0], n*20),
                                  (simulation.size[0] + ZOOM_VIEW_WIDTH,
                                   (n+1)*20)))
                display_surface.blit(i_surface, (simulation.size[0], n*20))

            # blit MARS visualization into display
            simulation.blit_into(display_surface, (0,0))
            pygame.display.update()
            clock.tick(30)

            to_remove = []
            for warrior in active_warriors:
                if not warrior.task_queue:
                    print("{} ({}) losses after {} cycles.".format(warrior.name,
                                                                    warrior.author,
                                                                    cycle))
                    warrior.losses += 1
                    to_remove.append(warrior)

            for warrior in to_remove:
                active_warriors.remove(warrior)

            # if there's only one left, or are all dead, then stop simulation
            if len(active_warriors) <= active_warrior_to_stop:
                for warrior in active_warriors:
                    print("{} ({}) wins after {} cycles.".format(warrior.name,
                                                                  warrior.author,
                                                                  cycle))
                    warrior.wins += 1
                break

            step = False
            while True:
                for event in pygame.event.get():
                    if event.type == QUIT:
                        # Tie all remaining bots and go to final results
                        next_round = True
                        stop_rounds = True
                        paused = False
                    elif event.type == KEYDOWN:
                        if event.key == K_SPACE:
                            # toggle pausing
                            paused = not paused
                        elif event.key == K_s:
                            # step simulation (and pause)
                            paused = True
                            step = True
                        elif event.key == K_n:
                            # Tie all remaining bots and go to next round
                            next_round = True

                if not paused or step or next_round:
                    break

            if next_round:
                for warrior in active_warriors:
                    if warrior.task_queue:
                        print("{} ({}) ties after {} cycles.".format(warrior.name,
                                                                    warrior.author,
                                                                    cycle))
                        warrior.ties += 1
                break
        else:
            # running until max cycles: tie
            for warrior in active_warriors:
                if warrior.task_queue:
                    print("{} ({}) ties after {} cycles.".format(warrior.name,
                                                                  warrior.author,
                                                                  cycle))
                    warrior.ties += 1

        if stop_rounds:
            break

    # print final results
    print()
    print("Final results: ({} rounds)".format(round))
    print("{} {} {} {}".format("Warrior (Author)".ljust(40), "wins".rjust(5),
                              "ties".rjust(5), "losses".rjust(5)))
    for warrior in warriors:
        print("{} {} {} {}".format(("{} ({})".format(warrior.name, warrior.author)).ljust(40),
                                  str(warrior.wins).rjust(5),
                                  str(warrior.ties).rjust(5),
                                  str(warrior.losses).rjust(5)))

    if not stop_rounds and not next_round:
        # keeps display open, until quit
        paused = True
        while paused:
            for event in pygame.event.get():
                if event.type == QUIT:
                    paused = False

    # exit pygame
    pygame.quit()


```

## File: corewar\corewar\mars.py

- Extension: .py
- Language: python
- Size: 25293 bytes
- Created: 2026-01-14 15:04:49
- Modified: 2026-01-14 15:04:49

### Code

```python
#! /usr/bin/env python
# coding: utf-8

from copy import copy
import operator
from random import randint

from .core import Core, DEFAULT_INITIAL_INSTRUCTION
from .redcode import *

__all__ = ['MARS', 'EVENT_EXECUTED', 'EVENT_I_WRITE', 'EVENT_I_READ',
           'EVENT_A_DEC', 'EVENT_A_INC', 'EVENT_B_DEC', 'EVENT_B_INC',
           'EVENT_A_READ', 'EVENT_A_WRITE', 'EVENT_B_READ', 'EVENT_B_WRITE',
           'EVENT_A_ARITH', 'EVENT_B_ARITH']

# Event types
EVENT_EXECUTED = 0
EVENT_I_WRITE  = 1
EVENT_I_READ   = 2
EVENT_A_DEC    = 3
EVENT_A_INC    = 4
EVENT_B_DEC    = 5
EVENT_B_INC    = 6
EVENT_A_READ   = 7
EVENT_A_WRITE  = 8
EVENT_B_READ   = 9
EVENT_B_WRITE  = 10
EVENT_A_ARITH  = 11
EVENT_B_ARITH  = 12

class MARS(object):
    """The MARS. Encapsulates a simulation.
    """

    def __init__(self, core=None, warriors=None, minimum_separation=100,
                 randomize=True, max_processes=None):
        self.core = core if core else Core()
        self.minimum_separation = minimum_separation
        self.max_processes = max_processes if max_processes else len(self.core)
        self.warriors = warriors if warriors else []
        if self.warriors:
            self.load_warriors(randomize)

    def core_event(self, warrior, address, event_type):
        """Supposed to be implemented by subclasses to handle core
           events.
        """
        i = self.core[address]
        assert isinstance(i.a_number, int), f"Expected int but got {type(i.a_number)}"
        assert isinstance(i.b_number, int), f"Expected int but got {type(i.b_number)}"
        i.a_number = min(max(i.a_number, -999999999), 999999999)
        i.b_number = min(max(i.b_number, -999999999), 999999999)
        assert i.a_number < 1000000000 and i.a_number > -1000000000, f"a_number out of bounds"
        assert i.b_number < 1000000000 and i.b_number > -1000000000, f"b_number out of bounds"

    def reset(self, clear_instruction=DEFAULT_INITIAL_INSTRUCTION):
        "Clears core and re-loads warriors."
        self.core.clear(clear_instruction)
        self.load_warriors()

    def load_warriors(self, randomize=True):
        "Loads its warriors to the memory with starting task queues"

        # the space between warriors - equally spaced in the core
        space = len(self.core) // len(self.warriors)

        for n, warrior in enumerate(self.warriors):
            # position is in the nth equally separated space plus a random
            # shift up to where the last instruction is minimum separated from
            # the first instruction of the next warrior
            warrior_position = (n * space)

            if randomize:
                warrior_position += randint(0, max(0, space -
                                                      len(warrior) -
                                                      self.minimum_separation))

            # add first and unique warrior task
            warrior.task_queue = [self.core.trim(warrior_position + warrior.start)]

            # copy warrior's instructions to the core
            for i, instruction in enumerate(warrior.instructions):
                self.core[warrior_position + i] = copy(instruction)
                self.core_event(warrior, warrior_position + i, EVENT_I_WRITE)

    def enqueue(self, warrior, address):
        """Enqueue another process into the warrior's task queue. Only if it's
           not already full.
        """
        if len(warrior.task_queue) < self.max_processes:
            warrior.task_queue.append(self.core.trim(address))

    def __iter__(self):
        return iter(self.core)

    def __len__(self):
        return len(self.core)

    def __getitem__(self, address):
        return self.core[address]

    def step(self):
        """Run one simulation step: execute one task of every active warrior.
        """
        for warrior in self.warriors:
            if warrior.task_queue:
                # The process counter is the next instruction-address in the
                # warrior's task queue
                pc = warrior.task_queue.pop(0)

                # copy the current instruction to the instruction register
                ir = copy(self.core[pc])

                # evaluate the A-operand
                if ir.a_mode == IMMEDIATE:
                    # if the mode is immediate, reading and writing a-pointers
                    # are zero
                    rpa = wpa = 0

                else:
                    # not immediate: direct or one of the indirect modes
                    rpa = self.core.trim_read(ir.a_number)
                    wpa = self.core.trim_write(ir.a_number)

                    if ir.a_mode != DIRECT:
                        # one of the indirect modes

                        # save this in case we need to use to post-increment
                        pip = pc + wpa

                        # pre-decrement, if needed
                        if ir.a_mode == PREDEC_A:
                            self.core[pc + wpa].a_number -= 1
                            self.core_event(warrior, pc + wpa, EVENT_A_DEC)
                        elif ir.a_mode == PREDEC_B:
                            self.core[pc + wpa].b_number -= 1
                            self.core_event(warrior, pc + wpa, EVENT_B_DEC)

                        # calculate the indirect address, from A or B number
                        if ir.a_mode in (PREDEC_A, INDIRECT_A, POSTINC_A):
                            rpa = self.core.trim_read(rpa + self.core[pc + rpa].a_number)
                            wpa = self.core.trim_write(wpa + self.core[pc + wpa].a_number)
                        else:
                            rpa = self.core.trim_read(rpa + self.core[pc + rpa].b_number)
                            wpa = self.core.trim_write(wpa + self.core[pc + wpa].b_number)

                # copy instruction pointer by A
                ira = copy(self.core[pc + rpa])

                # post-increment, if needed
                if ir.a_mode == POSTINC_A:
                    self.core[pip].a_number += 1
                    self.core_event(warrior, pip, EVENT_A_INC)
                elif ir.a_mode == POSTINC_B:
                    self.core[pip].b_number += 1
                    self.core_event(warrior, pip, EVENT_B_INC)

                # evaluate the B-operand - pretty much the same as A
                if ir.b_mode == IMMEDIATE:
                    rpb = wpb = 0
                else:
                    rpb = self.core.trim_read(ir.b_number)
                    wpb = self.core.trim_write(ir.b_number)

                    if ir.b_mode != DIRECT:
                        pip = pc + wpb

                        if ir.b_mode == PREDEC_A:
                            self.core[pc + wpb].a_number -= 1
                            self.core_event(warrior, pc + wpb, EVENT_A_DEC)
                        elif ir.b_mode == PREDEC_B:
                            self.core[pc + wpb].b_number -= 1
                            self.core_event(warrior, pc + wpb, EVENT_B_DEC)

                        if ir.b_mode in (PREDEC_A, INDIRECT_A, POSTINC_A):
                            rpb = self.core.trim_read(rpb + self.core[pc + rpb].a_number)
                            wpb = self.core.trim_write(wpb + self.core[pc + wpb].a_number)
                        else:
                            rpb = self.core.trim_read(rpb + self.core[pc + rpb].b_number)
                            wpb = self.core.trim_write(wpb + self.core[pc + wpb].b_number)

                irb = copy(self.core[pc + rpb])

                if ir.b_mode == POSTINC_A:
                    self.core[pip].a_number += 1
                    self.core_event(warrior, pip, EVENT_A_INC)
                elif ir.b_mode == POSTINC_B:
                    self.core[pip].b_number += 1
                    self.core_event(warrior, pip, EVENT_B_INC)

                # arithmetic common code
                def do_arithmetic(op):
                    try:
                        if ir.modifier == M_A:
                            self.core[pc + wpb].a_number = op(irb.a_number, ira.a_number)
                            self.core_event(warrior, pc + wpb, EVENT_A_WRITE)
                            self.core_event(warrior, pc + rpa, EVENT_A_READ)
                            self.core_event(warrior, pc + rpb, EVENT_A_READ)
                        elif ir.modifier == M_B:
                            self.core[pc + wpb].b_number = op(irb.b_number, ira.b_number)
                            self.core_event(warrior, pc + wpb, EVENT_B_WRITE)
                            self.core_event(warrior, pc + rpa, EVENT_B_READ)
                            self.core_event(warrior, pc + rpb, EVENT_B_READ)
                        elif ir.modifier == M_AB:
                            self.core[pc + wpb].b_number = op(irb.b_number, ira.a_number)
                            self.core_event(warrior, pc + wpb, EVENT_B_WRITE)
                            self.core_event(warrior, pc + rpa, EVENT_A_READ)
                            self.core_event(warrior, pc + rpb, EVENT_B_READ)
                        elif ir.modifier == M_BA:
                            self.core[pc + wpb].a_number = op(irb.b_number, ira.a_number)
                            self.core_event(warrior, pc + wpb, EVENT_A_WRITE)
                            self.core_event(warrior, pc + rpa, EVENT_A_READ)
                            self.core_event(warrior, pc + rpb, EVENT_B_READ)
                        elif ir.modifier == M_F or ir.modifier == M_I:
                            self.core[pc + wpb].a_number = op(irb.a_number, ira.a_number)
                            self.core[pc + wpb].b_number = op(irb.b_number, ira.b_number)
                            self.core_event(warrior, pc + wpb, EVENT_A_WRITE)
                            self.core_event(warrior, pc + wpb, EVENT_B_WRITE)
                            self.core_event(warrior, pc + rpa, EVENT_A_READ)
                            self.core_event(warrior, pc + rpb, EVENT_A_READ)
                            self.core_event(warrior, pc + rpa, EVENT_B_READ)
                            self.core_event(warrior, pc + rpb, EVENT_B_READ)
                        elif ir.modifier == M_X:
                            self.core[pc + wpb].b_number = op(irb.b_number, ira.a_number)
                            self.core[pc + wpb].a_number = op(irb.a_number, ira.b_number)
                            self.core_event(warrior, pc + wpb, EVENT_A_WRITE)
                            self.core_event(warrior, pc + wpb, EVENT_B_WRITE)
                            self.core_event(warrior, pc + rpa, EVENT_A_READ)
                            self.core_event(warrior, pc + rpb, EVENT_A_READ)
                            self.core_event(warrior, pc + rpa, EVENT_B_READ)
                            self.core_event(warrior, pc + rpb, EVENT_B_READ)
                        else:
                            raise ValueError("Invalid modifier: %d" % ir.modifier)

                        # enqueue next instruction
                        self.enqueue(warrior, pc + 1)
                    except ZeroDivisionError:
                        pass

                # comparison common code
                def do_comparison(cmp):
                    if ir.modifier == M_A:
                        self.enqueue(warrior,
                                     pc + (2 if cmp(ira.a_number, irb.a_number) else 1))
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + rpb, EVENT_A_READ)
                    elif ir.modifier == M_B:
                        self.enqueue(warrior,
                                     pc + (2 if cmp(ira.b_number, irb.b_number) else 1))
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                        self.core_event(warrior, pc + rpb, EVENT_B_READ)
                    elif ir.modifier == M_AB:
                        self.enqueue(warrior,
                                     pc + (2 if cmp(ira.a_number, irb.b_number) else 1))
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + rpb, EVENT_B_READ)
                    elif ir.modifier == M_BA:
                        self.enqueue(warrior,
                                     pc + (2 if cmp(ira.b_number, irb.a_number) else 1))
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                        self.core_event(warrior, pc + rpb, EVENT_A_READ)
                    elif ir.modifier == M_F:
                        self.enqueue(warrior,
                                     pc + (2 if cmp(ira.a_number, irb.a_number) and
                                                cmp(ira.b_number, irb.b_number) else 1))
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + rpb, EVENT_A_READ)
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                        self.core_event(warrior, pc + rpb, EVENT_B_READ)
                    elif ir.modifier == M_X:
                        self.enqueue(warrior,
                                     pc + (2 if cmp(ira.a_number, irb.b_number) and
                                                cmp(ira.b_number, irb.a_number) else 1))
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + rpb, EVENT_A_READ)
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                        self.core_event(warrior, pc + rpb, EVENT_B_READ)
                    elif ir.modifier == M_I:
                        self.enqueue(warrior,
                                     pc + (2 if ira == irb else 1))
                        self.core_event(warrior, pc + rpa, EVENT_I_READ)
                        self.core_event(warrior, pc + rpb, EVENT_I_READ)
                    else:
                        raise ValueError("Invalid modifier: %d" % ir.modifier)

                self.core_event(warrior, pc, EVENT_EXECUTED)

                if ir.opcode == DAT:
                    # does not enqueue next instruction, therefore, killing the
                    # process
                    pass
                elif ir.opcode == MOV:
                    if ir.modifier == M_A:
                        self.core[pc + wpb].a_number = ira.a_number
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + wpb, EVENT_A_WRITE)
                    elif ir.modifier == M_B:
                        self.core[pc + wpb].b_number = ira.b_number
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                        self.core_event(warrior, pc + wpb, EVENT_B_WRITE)
                    elif ir.modifier == M_AB:
                        self.core[pc + wpb].b_number = ira.a_number
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + wpb, EVENT_B_WRITE)
                    elif ir.modifier == M_BA:
                        self.core[pc + wpb].a_number = ira.b_number
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                        self.core_event(warrior, pc + wpb, EVENT_A_WRITE)
                    elif ir.modifier == M_F:
                        self.core[pc + wpb].a_number = ira.a_number
                        self.core[pc + wpb].b_number = ira.b_number
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                        self.core_event(warrior, pc + wpb, EVENT_A_WRITE)
                        self.core_event(warrior, pc + wpb, EVENT_B_WRITE)
                    elif ir.modifier == M_X:
                        self.core[pc + wpb].b_number = ira.a_number
                        self.core[pc + wpb].a_number = ira.b_number
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                        self.core_event(warrior, pc + wpb, EVENT_A_WRITE)
                        self.core_event(warrior, pc + wpb, EVENT_B_WRITE)
                    elif ir.modifier == M_I:
                        self.core[pc + wpb] = ira
                        self.core_event(warrior, pc + rpa, EVENT_I_READ)
                        self.core_event(warrior, pc + wpb, EVENT_I_WRITE)
                    else:
                        raise ValueError("Invalid modifier: %d" % ir.modifier)

                    # enqueue next instruction
                    self.enqueue(warrior, pc + 1)
                elif ir.opcode == ADD:
                    do_arithmetic(operator.add)
                elif ir.opcode == SUB:
                    do_arithmetic(operator.sub)
                elif ir.opcode == MUL:
                    do_arithmetic(operator.mul)
                elif ir.opcode == DIV:
                    do_arithmetic(operator.floordiv)
                elif ir.opcode == MOD:
                    do_arithmetic(operator.mod)
                elif ir.opcode == JMP:
                    self.enqueue(warrior, pc + rpa)
                elif ir.opcode == JMZ:
                    if ir.modifier == M_A or ir.modifier == M_BA:
                        self.enqueue(warrior, pc + (rpa if irb.a_number == 0 else 1))
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                    elif ir.modifier == M_B or ir.modifier == M_AB:
                        self.enqueue(warrior, pc + (rpa if irb.b_number == 0 else 1))
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                    elif ir.modifier in (M_F, M_X, M_I):
                        self.enqueue(warrior,
                                     pc + (rpa if irb.a_number == irb.b_number == 0 else 1))
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                    else:
                        raise ValueError("Invalid modifier: %d" % ir.modifier)
                elif ir.opcode == JMN:
                    if ir.modifier == M_A or ir.modifier == M_BA:
                        self.enqueue(warrior, pc + (rpa if irb.a_number != 0 else 1))
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                    elif ir.modifier == M_B or ir.modifier == M_AB:
                        self.enqueue(warrior, pc + (rpa if irb.b_number != 0 else 1))
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                    elif ir.modifier in (M_F, M_X, M_I):
                        self.enqueue(warrior,
                                     pc + (rpa if irb.a_number != 0 or
                                                  irb.b_number != 0 else 1))
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                    else:
                        raise ValueError("Invalid modifier: %d" % ir.modifier)
                elif ir.opcode == DJN:
                    if ir.modifier == M_A or ir.modifier == M_BA:
                        self.core[pc + wpb].a_number -= 1
                        irb.a_number -= 1
                        self.enqueue(warrior, pc + (rpa if irb.a_number != 0 else 1))
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + rpa, EVENT_A_DEC)
                    elif ir.modifier == M_B or ir.modifier == M_AB:
                        self.core[pc + wpb].b_number -= 1
                        irb.b_number -= 1
                        self.enqueue(warrior, pc + (rpa if irb.b_number != 0 else 1))
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                        self.core_event(warrior, pc + rpa, EVENT_B_DEC)
                    elif ir.modifier in (M_F, M_X, M_I):
                        self.core[pc + wpb].a_number -= 1
                        irb.a_number -= 1
                        self.core[pc + wpb].b_number -= 1
                        irb.b_number -= 1
                        self.enqueue(warrior,
                                     pc + (rpa if irb.a_number != 0 or
                                                  irb.b_number != 0 else 1))
                        self.core_event(warrior, pc + rpa, EVENT_A_READ)
                        self.core_event(warrior, pc + rpa, EVENT_B_READ)
                        self.core_event(warrior, pc + rpa, EVENT_A_DEC)
                        self.core_event(warrior, pc + rpa, EVENT_B_DEC)
                    else:
                        raise ValueError("Invalid modifier: %d" % ir.modifier)
                elif ir.opcode == SPL:
                    self.enqueue(warrior, pc + 1)
                    self.enqueue(warrior, pc + rpa)
                elif ir.opcode == SLT:
                    do_comparison(operator.lt)
                elif ir.opcode == CMP or ir.opcode == SEQ:
                    do_comparison(operator.eq)
                elif ir.opcode == SNE:
                    do_comparison(operator.ne)
                elif ir.opcode == NOP:
                    self.enqueue(warrior, pc + 1)
                else:
                    raise ValueError("Invalid opcode: %d" % ir.opcode)

if __name__ == "__main__":
    import argparse
    import redcode

    parser = argparse.ArgumentParser(description='MARS (Memory Array Redcode Simulator)')
    parser.add_argument('--rounds', '-r', metavar='ROUNDS', type=int, nargs='?',
                        default=1, help='Rounds to play')
    parser.add_argument('--size', '-s', metavar='CORESIZE', type=int, nargs='?',
                        default=8000, help='The core size')
    parser.add_argument('--cycles', '-c', metavar='CYCLES', type=int, nargs='?',
                        default=80000, help='Cycles until tie')
    parser.add_argument('--processes', '-p', metavar='MAXPROCESSES', type=int, nargs='?',
                        default=8000, help='Max processes')
    parser.add_argument('--length', '-l', metavar='MAXLENGTH', type=int, nargs='?',
                        default=100, help='Max warrior length')
    parser.add_argument('--distance', '-d', metavar='MINDISTANCE', type=int, nargs='?',
                        default=100, help='Minimum warrior distance')
    parser.add_argument('warriors', metavar='WARRIOR', type=file, nargs='+',
                        help='Warrior redcode filename')

    args = parser.parse_args()

    # build environment
    environment = {'CORESIZE': args.size,
                   'CYCLES': args.cycles,
                   'ROUNDS': args.rounds,
                   'MAXPROCESSES': args.processes,
                   'MAXLENGTH': args.length,
                   'MINDISTANCE': args.distance}

    # assemble warriors
    warriors = [redcode.parse(file, environment) for file in args.warriors]

    # initialize wins, losses and ties for each warrior
    for warrior in warriors:
        warrior.wins = warrior.ties = warrior.losses = 0

    # for each round
    for i in range(args.rounds):

        # create new simulation
        simulation = MARS(warriors=warriors,
                          minimum_separation = args.distance,
                          max_processes = args.processes)

        active_warrior_to_stop = 1 if len(warriors) >= 2 else 0

        for c in range(args.cycles):
            simulation.step()

            # if there's only one left, or are all dead, then stop simulation
            if sum(1 if warrior.task_queue else 0 for warrior in warriors) <= active_warrior_to_stop:
                for warrior in warriors:
                    if warrior.task_queue:
                        warrior.wins += 1
                    else:
                        warrior.losses += 1
                break
        else:
            # running until max cycles: tie
            for warrior in warriors:
                if warrior.task_queue:
                    warrior.ties += 1
                else:
                    warrior.losses += 1

    # print results
    print("Results: ({} rounds)".format(args.rounds))
    print("{} {} {} {}".format("Warrior (Author)".ljust(40), "wins".rjust(5),
                              "ties".rjust(5), "losses".rjust(5)))
    for warrior in warriors:
        print("{} {} {} {}".format(("{} ({})".format(warrior.name, warrior.author)).ljust(40),
                                  str(warrior.wins).rjust(5),
                                  str(warrior.ties).rjust(5),
                                  str(warrior.losses).rjust(5)))



```

## File: corewar\corewar\redcode.py

- Extension: .py
- Language: python
- Size: 15594 bytes
- Created: 2026-01-14 15:04:49
- Modified: 2026-01-14 15:04:49

### Code

```python
# coding: utf-8

from copy import copy
import re

__all__ = ['parse', 'DAT', 'MOV', 'ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'JMP',
           'JMZ', 'JMN', 'DJN', 'SPL', 'SLT', 'CMP', 'SEQ', 'SNE', 'NOP',
           'M_A', 'M_B', 'M_AB', 'M_BA', 'M_F', 'M_X', 'M_I', 'IMMEDIATE',
           'DIRECT', 'INDIRECT_B', 'PREDEC_B', 'POSTINC_B', 'INDIRECT_A',
           'PREDEC_A', 'POSTINC_A', 'Instruction', 'Warrior']

DAT = 0     # terminate process
MOV = 1     # move from A to B
ADD = 2     # add A to B, store result in B
SUB = 3     # subtract A from B, store result in B
MUL = 4     # multiply A by B, store result in B
DIV = 5     # divide B by A, store result in B if A <> 0, else terminate
MOD = 6     # divide B by A, store remainder in B if A <> 0, else terminate
JMP = 7     # transfer execution to A
JMZ = 8     # transfer execution to A if B is zero
JMN = 9     # transfer execution to A if B is non-zero
DJN = 10    # decrement B, if B is non-zero, transfer execution to A
SPL = 11    # split off process to A
SLT = 12    # skip next instruction if A is less than B
CMP = 13    # same as SEQ
SEQ = 14    # Skip next instruction if A is equal to B
SNE = 15    # Skip next instruction if A is not equal to B
NOP = 16    # No operation

# Instructions read and write A-fields.
M_A = 0

# Instructions read and write B-fields.
M_B = 1

# Instructions read the A-field of the A-instruction and the B-field of the
# B-instruction and write to B-fields.
M_AB = 2

# Instructions read the B-field of the A-instruction and the A-field of the
# B-instruction and write to A-fields.
M_BA = 3

# Instructions read both A- and B-fields of the A and B-instruction and
# write to both A- and B-fields (A to A and B to B).
M_F = 4

# Instructions read both A- and B-fields of the A and B-instruction  and
# write  to both A- and B-fields exchanging fields (A to B and B to A).
M_X = 5

# Instructions read and write entire instructions.
M_I = 6

IMMEDIATE = 0   # immediate
DIRECT = 1      # direct
INDIRECT_B = 2  # indirect using B-field
PREDEC_B  = 3   # predecrement indirect using B-field
POSTINC_B = 4   # postincrement indirect using B-field
INDIRECT_A = 5  # indirect using A-field
PREDEC_A = 6    # predecrement indirect using A-field
POSTINC_A = 7   # postincrement indirect using A-field

INSTRUCTION_REGEX = re.compile(r'([a-z]{3})'  # opcode
                               r'(?:\s*\.\s*([abfxi]{1,2}))?' # optional modifier
                               r'(?:\s*([#\$\*@\{<\}>])?\s*([^,$]+))?' # optional first value
                               r'(?:\s*,\s*([#\$\*@\{<\}>])?\s*(.+))?$', # optional second value
                               re.I)

OPCODES = {'DAT': DAT, 'MOV': MOV, 'ADD': ADD, 'SUB': SUB, 'MUL': MUL,
           'DIV': DIV, 'MOD': MOD, 'JMP': JMP, 'JMZ': JMZ, 'JMN': JMN,
           'DJN': DJN, 'SPL': SPL, 'SLT': SLT, 'CMP': CMP, 'SEQ': SEQ,
           'SNE': SNE, 'NOP': NOP}

MODIFIERS = {'A': M_A, 'B': M_B, 'AB': M_AB, 'BA': M_BA, 'F': M_F, 'X': M_X,
             'I': M_I}

MODES = { '#': IMMEDIATE, '$': DIRECT, '@': INDIRECT_B, '<': PREDEC_B,
          '>': POSTINC_B, '*': INDIRECT_A, '{': PREDEC_A, '}': POSTINC_A }

# ICWS'88 to ICWS'94 Conversion
# The default modifier for ICWS'88 emulation is determined according to the
# table below.
#        Opcode                             A-mode    B-mode    modifier
DEFAULT_MODIFIERS = {
        ('DAT', 'NOP')                 : {('#$@<>', '#$@<>'): 'F'},
        ('MOV','CMP')                  : {('#'    , '#$@<>'): 'AB',
                                          ('$@<>' , '#'    ): 'B' ,
                                          ('$@<>' , '$@<>' ): 'I'},
        ('ADD','SUB','MUL','DIV','MOD'): {('#'    , '#$@<>'): 'AB',
                                          ('$@<>' , '#'    ): 'B' ,
                                          ('$@<>' , '$@<>' ): 'F'},
        ('SLT', 'SEQ', 'SNE')          : {('#'    , '#$@<>'): 'AB',
                                          ('$@<>' , '#$@<>'): 'B'},
        ('JMP','JMZ','JMN','DJN','SPL'): {('#$@<>', '#$@<>'): 'B'}
    }

# Transform the readable form above, into the internal representation
DEFAULT_MODIFIERS = dict((tuple(OPCODES[opcode] for opcode in opcodes),
                         dict(((tuple(MODES[a] for a in ab_modes[0]),
                                tuple(MODES[b] for b in ab_modes[1])),
                               MODIFIERS[modifier]) for ab_modes, modifier in ab_modes_modifiers.items()))
                         for opcodes, ab_modes_modifiers in DEFAULT_MODIFIERS.items())

class Warrior(object):
    "An encapsulation of a Redcode Warrior, with instructions and meta-data"

    def __init__(self, name='Unnamed', author='Anonymous', date=None,
                 version=None, strategy=None, start=0):
        self.name = name
        self.author = author
        self.date = date
        self.version = version
        self.strategy = strategy
        self.start = start
        self.instructions = []

    def __iter__(self):
        return iter(self.instructions)

    def __len__(self):
        return len(self.instructions)

    def __repr__(self):
        return "<Warrior name=%s %d instructions>" % (self.name, len(self.instructions))

class Instruction(object):
    "An encapsulation of a Redcode instruction."

    def __init__(self, opcode, modifier=None, a_mode=None, a_number=0,
                 b_mode=None, b_number=0):
        self.opcode = OPCODES[opcode.upper()] if isinstance(opcode, str) else opcode
        if a_mode is not None:
            self.a_mode = MODES[a_mode] if isinstance(a_mode, str) else a_mode
        else:
            self.a_mode = DIRECT
        if b_mode is not None:
            self.b_mode = MODES[b_mode] if isinstance(b_mode, str) else b_mode
        else:
            self.b_mode = IMMEDIATE if self.opcode == DAT and a_number != None else DIRECT
        self._a_number = a_number if a_number else 0
        self._b_number = b_number if b_number else 0

        # this should be last, to decide on the default modifier
        if modifier is not None:
            self.modifier = MODIFIERS[modifier.upper()] if isinstance(modifier, str) else modifier
        else:
            self.modifier = self.default_modifier()

        self.core = None

    def core_binded(self, core):
        """Return a copy of this instruction binded to a Core.
        """
        instruction = copy(self)
        instruction.core = core
        return instruction

    def default_modifier(self):
        for opcodes, modes_modifiers in DEFAULT_MODIFIERS.items():
            if self.opcode in opcodes:
                for ab_modes, modifier in modes_modifiers.items():
                    a_modes, b_modes = ab_modes
                    if self.a_mode in a_modes and self.b_mode in b_modes:
                        return modifier
        raise RuntimeError("Error getting default modifier")

    @property
    def a_number(self):
        return self._a_number

    @property
    def b_number(self):
        return self._b_number

    @a_number.setter
    def a_number(self, number):
        self._a_number = self.core.trim_signed(number) if self.core else number

    @b_number.setter
    def b_number(self, number):
        self._b_number = self.core.trim_signed(number) if self.core else number

    def __eq__(self, other):
        return (self.opcode == other.opcode and self.modifier == other.modifier and
                self.a_mode == other.a_mode and self.a_number == other.a_number and
                self.b_mode == other.b_mode and self.b_number == other.b_number)

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        # inverse lookup the instruction values
        opcode   = next(key for key,value in OPCODES.items() if value==self.opcode)
        modifier = next(key for key,value in MODIFIERS.items() if value==self.modifier)
        a_mode   = next(key for key,value in MODES.items() if value==self.a_mode)
        b_mode   = next(key for key,value in MODES.items() if value==self.b_mode)

        return "%s.%s %s %s, %s %s" % (opcode,
                                       modifier.ljust(2),
                                       a_mode,
                                       str(self.a_number).rjust(5),
                                       b_mode,
                                       str(self.b_number).rjust(5))

    def __repr__(self):
        return "<%s>" % self

def parse(input, definitions={}):
    """ Parse a Redcode code from a line iterator (input) returning a Warrior
        object."""

    found_recode_info_comment = False
    labels = {}
    code_address = 0

    warrior = Warrior()
    warrior.strategy = []

    # use a version of environment because we're going to add names to it
    environment = copy(definitions)

    # first pass
    for n, line in enumerate(input):
        line = line.strip()
        if line:
            # process info comments
            m = re.match(r'^;redcode\w*$', line, re.I)
            if m:
                if found_recode_info_comment:
                    # stop reading, found second ;redcode
                    break;
                else:
                    # first ;redcode ignore all input before
                    warrior.instructions = []
                    labels = {}
                    environment = copy(definitions)
                    code_address = 0
                    found_recode_info_comment = True
                continue

            m = re.match(r'^;name\s+(.+)$', line, re.I)
            if m:
                warrior.name = m.group(1).strip()
                continue

            m = re.match(r'^;author\s+(.+)$', line, re.I)
            if m:
                warrior.author = m.group(1).strip()
                continue

            m = re.match(r'^;date\s+(.+)$', line, re.I)
            if m:
                warrior.date = m.group(1).strip()
                continue

            m = re.match(r'^;version\s+(.+)$', line, re.I)
            if m:
                warrior.version = m.group(1).strip()
                continue

            m = re.match(r'^;strat(?:egy)?\s+(.+)$', line, re.I)
            if m:
                warrior.strategy.append(m.group(1).strip())
                continue

            # Test if assert expression evaluates to true
            m = re.match(r'^;assert\s+(.+)$', line, re.I)
            if m:
                if not eval(m.group(1), environment):
                    raise AssertionError("Assertion failed: %s, line %d" % (line, n))
                continue

            # ignore other comments
            m = re.match(r'^([^;]*)\s*;', line)
            if m:
                # rip off comment from the line
                line = m.group(1).strip()
                # if this is a comment line
                if not line: continue

            # Match ORG
            m = re.match(r'^ORG\s+(.+)\s*$', line, re.I)
            if m:
                warrior.start = m.group(1)
                continue

            # Match END
            m = re.match(r'^END(?:\s+([^\s]+))?$', line, re.I)
            if m:
                if m.group(1):
                    warrior.start = m.group(1)
                break # stop processing (end of redcode)

            # Match EQU
            m = re.match(r'^([a-z]\w*)\s+EQU\s+(.*)\s*$', line, re.I)
            if m:
                name, value = m.groups()
                # evaluate EQU expression using previous EQU definitions,
                # add result to a name variable in environment
                environment[name] = eval(value, environment)
                continue

            # Keep matching the first word until it's no label anymore
            while True:
                m = re.match(r'^([a-z]\w*)\s+(.+)\s*$', line)
                if m:
                    label_candidate = m.group(1)
                    if label_candidate.upper() not in OPCODES:
                        labels[label_candidate] = code_address

                        # strip label off and keep looking
                        line = m.group(2)
                        continue
                # its an instruction, not label. proceed OR no match, probably
                # a all-value-omitted instruction.
                break

            # At last, it should match an instruction
            m = INSTRUCTION_REGEX.match(line)
            if not m:
                raise ValueError('Error at line %d: expected instruction in expression: "%s"' %
                                 (n, line))
            else:
                opcode, modifier, a_mode, a_number, b_mode, b_number = m.groups()

                if opcode.upper() not in OPCODES:
                    raise ValueError('Invalid opcode: %s in line %d: "%s"' %
                                     (opcode, n, line))
                if modifier is not None and modifier.upper() not in MODIFIERS:
                    raise ValueError('Invalid modifier: %s in line %d: "%s"' %
                                     (modifier, n, line))

                # add parts of instruction read. the fields should be parsed
                # as an expression in the second pass, to expand labels
                warrior.instructions.append(Instruction(opcode, modifier,
                                                        a_mode, a_number,
                                                        b_mode, b_number))

            # increment code counting
            code_address += 1


    # join strategy lines with line breaks
    warrior.strategy = '\n'.join(warrior.strategy)

    # evaluate start expression
    if isinstance(warrior.start, str):
        warrior.start = eval(warrior.start, environment, labels)

    # second pass
    for n, instruction in enumerate(warrior.instructions):

        # create a dictionary of relative labels addresses to be used as a local
        # eval environment
        relative_labels = dict((name, address-n) for name, address in labels.items())

        # evaluate instruction fields using global environment and labels
        if isinstance(instruction.a_number, str):
            instruction.a_number = eval(instruction.a_number, environment, relative_labels)
        if isinstance(instruction.b_number, str):
            instruction.b_number = eval(instruction.b_number, environment, relative_labels)
    
    for i in warrior.instructions:
        assert isinstance(i.opcode, int), f"opcode is not an int: {i.opcode}"
        assert i.opcode>=0 and i.opcode<=16, f"opcode is not in range 0-16: {i.opcode}"
        assert isinstance(i.modifier, int), f"modifier is not an int: {i.modifier}"
        assert i.modifier>=0 and i.modifier<=6, f"modifier is not in range 0-6: {i.modifier}"
        assert isinstance(i.a_number, int), f"a_number is not an int: {i.a_number}"
        assert isinstance(i.b_number, int), f"b_number is not an int: {i.b_number}"
        assert isinstance(i.a_mode, int), f"a_mode is not an int: {i.a_mode}"
        assert i.a_mode>=0 and i.a_mode<=7, f"a_mode is not in range 0-7: {i.a_mode}"
        assert isinstance(i.b_mode, int), f"b_mode is not an int: {i.b_mode}"
        assert i.b_mode>=0 and i.b_mode<=7, f"b_mode is not in range 0-7: {i.b_mode}"

    return warrior


```

## File: corewar\corewar\viz.py

- Extension: .py
- Language: python
- Size: 19138 bytes
- Created: 2026-01-14 15:04:49
- Modified: 2026-01-14 15:04:49

### Code

```python
#! /usr/bin/env python
# coding: utf-8

import pygame
from pygame.locals import *

from core import DEFAULT_INITIAL_INSTRUCTION
from mars import *
from redcode import *
import os

INSTRUCTIONS_PER_LINE = 100
INSTRUCTION_SIZE_X = 9
INSTRUCTION_SIZE_Y = 9

ZOOM_VIEW_WIDTH = 200

I_SIZE = (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)
I_AREA = ((0,0), I_SIZE)

IMAGE_BG_COLOR = (255,255,254,255)
IMAGE_FG_COLOR = (0,0,1,255)

OPCODE_SURFACES = None

DEFAULT_BG_COLOR = (0, 0, 0)
DEFAULT_FG_COLOR = (60,60,60)
BLACK = (0, 0, 0)
WHITE = (255,255,255)

# Colors are dark and bright
WARRIOR_COLORS_ = (((0,0,100), (0,0,255)),
                  ((0,100,0), (0,255,0)),
                  ((0,100,100), (0,255,255)),
                  ((100,0,0), (255,0,0)),
                  ((100,0,100), (255,0,255)),
                  ((100,100,0), (255,255,0)))


WARRIOR_COLORS_ = (((127, 0, 0), (255, 0, 0)),
 ((127, 67, 0), (255, 135, 0)),
 ((127, 105, 0), (255, 211, 0)),
 ((111, 127, 5), (222, 255, 10)),
 ((80, 127, 5), (161, 255, 10)),
 ((5, 127, 76), (10, 255, 153)),
 ((5, 119, 127), (10, 239, 255)),
 ((10, 62, 122), (20, 125, 245)),
 ((44, 5, 127), (88, 10, 255)),
 ((95, 5, 127), (190, 10, 255)))

WARRIOR_COLORS_ = (((0, 9, 12), (0, 18, 25)),
 ((0, 47, 57), (0, 95, 115)),
 ((5, 73, 75), (10, 147, 150)),
 ((74, 105, 94), (148, 210, 189)),
 ((116, 108, 83), (233, 216, 166)),
 ((119, 77, 0), (238, 155, 0)),
 ((101, 51, 1), (202, 103, 2)),
 ((93, 31, 1), (187, 62, 3)),
 ((87, 16, 9), (174, 32, 18)),
 ((77, 17, 19), (155, 34, 38)))


WARRIOR_COLORS = (((124, 32, 34), (249, 65, 68)),
 ((121, 57, 22), (243, 114, 44)),
 ((124, 75, 15), (248, 150, 30)),
 ((124, 66, 37), (249, 132, 74)),
 ((124, 99, 39), (249, 199, 79)),
 ((72, 95, 54), (144, 190, 109)),
 ((33, 85, 69), (67, 170, 139)),
 ((38, 72, 71), (77, 144, 142)),
 ((43, 58, 72), (87, 117, 144)),
 ((19, 62, 80), (39, 125, 161)))


def load_opcode_surfaces():
    "Load the images of the opcodes from the file"
    all_instructions = pygame.image.load('pixels/instructions.png')
    class Y:
        y = -INSTRUCTION_SIZE_Y
        def __call__(self):
            self.y += INSTRUCTION_SIZE_Y
            return self.y
    y = Y()

    return {
        DAT: all_instructions.subsurface(((0,y()), I_SIZE)),
        MOV: all_instructions.subsurface(((0,y()), I_SIZE)),
        ADD: all_instructions.subsurface(((0,y()), I_SIZE)),
        SUB: all_instructions.subsurface(((0,y()), I_SIZE)),
        MUL: all_instructions.subsurface(((0,y()), I_SIZE)),
        DIV: all_instructions.subsurface(((0,y()), I_SIZE)),
        MOD: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMP: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMZ: all_instructions.subsurface(((0,y()), I_SIZE)),
        JMN: all_instructions.subsurface(((0,y()), I_SIZE)),
        DJN: all_instructions.subsurface(((0,y()), I_SIZE)),
        SPL: all_instructions.subsurface(((0,y()), I_SIZE)),
        SLT: all_instructions.subsurface(((0,y()), I_SIZE)),
        CMP: all_instructions.subsurface(((0,y()), I_SIZE)),
        SEQ: all_instructions.subsurface(((0,y()), I_SIZE)),
        SNE: all_instructions.subsurface(((0,y()), I_SIZE)),
        NOP: all_instructions.subsurface(((0,y()), I_SIZE))}

def opcode_surface(opcode, foreground=None, background=None):
    "Return a surface representing an instruction in the core"
    surface = pygame.Surface(I_SIZE)
    opcode_surface = OPCODE_SURFACES[opcode].convert(surface)

    if background:
        surface.fill(background) # fill background color
        opcode_surface.set_colorkey(IMAGE_BG_COLOR) # make image bg transparent
        surface.blit(opcode_surface, (0,0)) # blit opcode in background
        surface.set_colorkey(IMAGE_FG_COLOR) # make image fg transparent

    if foreground:
        fg_surface = pygame.Surface(I_SIZE)
        fg_surface.fill(foreground) # fill foreground color
        opcode_surface.set_colorkey(IMAGE_FG_COLOR) # make image fg transparent
        fg_surface.blit(opcode_surface, (0,0)) # blit opcode in background
        fg_surface.set_colorkey(IMAGE_BG_COLOR) # make image bg transparent

        surface.blit(fg_surface, (0,0)) # blit in background

    return surface

class PygameMARS(MARS):
    "A MARS with a surface drawing of the core"

    def __init__(self, *args, **kargs):
        super(PygameMARS, self).__init__(*args, **kargs)
        self.size = (INSTRUCTION_SIZE_X * INSTRUCTIONS_PER_LINE,
                     INSTRUCTION_SIZE_Y * (len(self) // INSTRUCTIONS_PER_LINE))
        self.core_surface = pygame.Surface(self.size)
        self.recent_events = pygame.Surface(self.size)
        self.recent_events.set_colorkey(DEFAULT_BG_COLOR)

    def reset(self, clear_instruction=DEFAULT_INITIAL_INSTRUCTION):
        self.core.clear(clear_instruction)
        for n, instruction in enumerate(self):
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  DEFAULT_FG_COLOR,
                                                  DEFAULT_BG_COLOR),
                                   ((n % INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_X,
                                    (n // INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_Y))
        self.load_warriors()

    def load_warriors(self):
        super(PygameMARS, self).load_warriors()
        for instruction in self:
            instruction.fg_color = DEFAULT_FG_COLOR
            instruction.bg_color = DEFAULT_BG_COLOR

    def step(self):
        self.recent_events.fill(DEFAULT_BG_COLOR)
        super(PygameMARS, self).step()

    def blit_into(self, surface, dest):
        surface.blit(self.core_surface, dest)
        surface.blit(self.recent_events, dest)

    def core_event(self, warrior, address, event_type):
        address %= len(self)
        position = ((address % INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_X,
                    (address // INSTRUCTIONS_PER_LINE) * INSTRUCTION_SIZE_Y)
        instruction = self.core[address]

        if event_type in (EVENT_I_WRITE, EVENT_A_WRITE, EVENT_B_WRITE):
            # In case of a write event, we write the foreground with the
            # warrior's color
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  warrior.color[1],
                                                  None),
                                   position, area=I_AREA)
            self.recent_events.blit(opcode_surface(instruction.opcode,
                                                   WHITE,
                                                   DEFAULT_BG_COLOR),
                                    position, area=I_AREA)
            instruction.fg_color = warrior.color[1]
        elif event_type == EVENT_EXECUTED:
            # In case of execution, we write the background with warrior's color
            self.core_surface.blit(opcode_surface(instruction.opcode,
                                                  WHITE,
                                                  warrior.color[0]),
                                   position, area=I_AREA)
            self.recent_events.blit(opcode_surface(instruction.opcode,
                                                   BLACK,
                                                   warrior.color[1]),
                                    position, area=I_AREA)
            instruction.fg_color = WHITE
            instruction.bg_color = warrior.color[0]
        elif event_type in (EVENT_A_ARITH, EVENT_B_ARITH, EVENT_A_DEC,
                            EVENT_B_DEC, EVENT_A_INC, EVENT_B_INC):
            # In case of arithmetic modification, or increment/decrement, we
            # write a rectangle around the instruction
            pygame.draw.rect(self.core_surface, warrior.color[0],
                             (position, (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)),
                              1)
            pygame.draw.rect(self.recent_events, warrior.color[1],
                             (position, (INSTRUCTION_SIZE_X, INSTRUCTION_SIZE_Y)),
                              1)


if __name__ == "__main__":
    # import argparse
    from dataclasses import dataclass
    import tyro
    import sys

    # parser = argparse.ArgumentParser(description='MARS (Memory Array Redcode Simulator)')
    # parser.add_argument('--rounds', '-r', metavar='ROUNDS', type=int, nargs='?',
    #                     default=1, help='Rounds to play')
    # parser.add_argument('--paused', action='store_true', default=False,
    #                     help='Start each round paused')
    # parser.add_argument('--size', '-s', metavar='CORESIZE', type=int, nargs='?',
    #                     default=8000, help='The core size')
    # parser.add_argument('--cycles', '-c', metavar='CYCLES', type=int, nargs='?',
    #                     default=80000, help='Cycles until tie')
    # parser.add_argument('--processes', '-p', metavar='MAXPROCESSES', type=int, nargs='?',
    #                     default=8000, help='Max processes')
    # parser.add_argument('--length', '-l', metavar='MAXLENGTH', type=int, nargs='?',
    #                     default=100, help='Max warrior length')
    # parser.add_argument('--distance', '-d', metavar='MINDISTANCE', type=int, nargs='?',
    #                     default=100, help='Minimum warrior distance')
    # parser.add_argument('warriors', metavar='WARRIOR', type=str, nargs='+',
    #                     help='Warrior redcode filename')
    @dataclass
    class Args:
        # warriors: list[str] # List of warrior redcode filenames
        rounds: int = 100 # Rounds to play
        paused: bool | None = False # Start each round paused
        size: int = 8000 # The core size
        cycles: int = 80000 # Cycles until tie
        processes: int = 8000 # Max processes
        length: int = 100 # Max warrior length
        distance: int = 100 # Minimum warrior distance
        seed: int = 0

        warrior_dir: str | None = None
        start_cycles: int = 0

    args = tyro.cli(Args)

    import numpy as np
    import random
    np.random.seed(args.seed)
    random.seed(args.seed)


    # if len(args.warriors) > len(WARRIOR_COLORS):
        # print("Please specify a maximum of {} warriors.".format(len(WARRIOR_COLORS)), file=sys.stderr)
        # sys.exit(1)

    # build environment
    environment = {'CORESIZE': args.size,
                   'CYCLES': args.cycles,
                   'ROUNDS': args.rounds,
                   'MAXPROCESSES': args.processes,
                   'MAXLENGTH': args.length,
                   'MINDISTANCE': args.distance}

    # assemble warriors
    # warriors = [parse(file, environment) for file in args.warriors]
    # warriors = []
    # for file in args.warriors:
    #     with open(file, encoding="utf-8", errors="replace") as f:
    #         warrior = parse(f.readlines(), environment)
    #         warriors.append(warrior)
    
    def load_warriors(warrior_files):
        warriors = []
        for file in warrior_files:
            with open(file, encoding="utf-8", errors="replace") as f:
                warrior = parse(f.readlines(), environment)
                warriors.append(warrior)
        return warriors
    
    warrior_files = [os.path.join(args.warrior_dir, wf) for wf in os.listdir(args.warrior_dir)]
    all_warriors = load_warriors(warrior_files)
    # warriors = all_warriors[100:106]
    warriors = np.random.choice(all_warriors, 6, replace=False)

    # raise ValueError

    # initialize wins, losses, ties and color for each warrior
    for warrior, color in zip(warriors, WARRIOR_COLORS):
        warrior.wins = warrior.ties = warrior.losses = 0
        warrior.color = color

    # create MARS
    simulation = PygameMARS(minimum_separation = args.distance,
                            max_processes = args.processes)
    simulation.warriors = warriors

    # initialize pygame engine
    pygame.init()

    # core instruction's font
    core_font = pygame.font.SysFont("monospace", 12)

    # Load surfaces from file
    OPCODE_SURFACES = load_opcode_surfaces()

    # create display
    display_surface = pygame.display.set_mode((simulation.size[0] + ZOOM_VIEW_WIDTH,
                                               simulation.size[1]))

    # initializations
    c_address = 0

    # control variables
    paused = False
    stop_rounds = False

    # create clock to control FPS
    clock = pygame.time.Clock()

    # for each round
    for round in range(1, args.rounds + 1):
        warriors = np.random.choice(all_warriors, 10, replace=False)
        for warrior, color in zip(warriors, WARRIOR_COLORS):
            warrior.wins = warrior.ties = warrior.losses = 0
            warrior.color = color
        simulation.warriors = warriors

        # reset simulation and load warriors
        simulation.reset()
        for _ in range(args.start_cycles):
            simulation.step()

        # start with all warriors active
        active_warriors = list(warriors)

        # how many warriors should be playing to skip to next round
        active_warrior_to_stop = 1 if len(warriors) >= 2 else 0

        # start paused if user requested from command line
        if args.paused:
            paused = True

        # control variable
        next_round = False

        print()
        print("Starting round {}".format(round))

        for cycle in range(args.cycles):
            # step one simulation in MARS
            simulation.step()

            # get mouse position
            mouse_pos = pygame.mouse.get_pos()
            # calculate address based on mouse position if position is over core
            if 0 <= mouse_pos[0] <= simulation.size[0] and 0 <= mouse_pos[1] <= simulation.size[1]:
                c_address = (INSTRUCTIONS_PER_LINE * (mouse_pos[1]//INSTRUCTION_SIZE_Y) +
                             (mouse_pos[0] // INSTRUCTION_SIZE_X))

            # clear display part of instructions
            display_surface.fill(BLACK, ((simulation.size[0], 0),
                                         (ZOOM_VIEW_WIDTH, simulation.size[1])))
            for n, address in enumerate(range(c_address-18, c_address+18)):
                instruction = simulation[address]
                i_surface = core_font.render("%04d %s" % (address,
                                                          instruction),
                                               True,
                                               instruction.fg_color)
                pygame.draw.rect(display_surface, instruction.bg_color,
                                 ((simulation.size[0], n*20),
                                  (simulation.size[0] + ZOOM_VIEW_WIDTH,
                                   (n+1)*20)))
                display_surface.blit(i_surface, (simulation.size[0], n*20))

            # blit MARS visualization into display
            simulation.blit_into(display_surface, (0,0))
            pygame.display.update()
            clock.tick(120)

            to_remove = []
            for warrior in active_warriors:
                if not warrior.task_queue:
                    print("{} ({}) losses after {} cycles.".format(warrior.name,
                                                                    warrior.author,
                                                                    cycle))
                    warrior.losses += 1
                    to_remove.append(warrior)

            for warrior in to_remove:
                active_warriors.remove(warrior)

            # if there's only one left, or are all dead, then stop simulation
            if len(active_warriors) <= active_warrior_to_stop:
                for warrior in active_warriors:
                    print("{} ({}) wins after {} cycles.".format(warrior.name,
                                                                  warrior.author,
                                                                  cycle))
                    warrior.wins += 1
                break

            step = False
            while True:
                for event in pygame.event.get():
                    if event.type == QUIT:
                        # Tie all remaining bots and go to final results
                        next_round = True
                        stop_rounds = True
                        paused = False
                    elif event.type == KEYDOWN:
                        if event.key == K_SPACE:
                            # toggle pausing
                            paused = not paused
                        elif event.key == K_s:
                            # step simulation (and pause)
                            paused = True
                            step = True
                        elif event.key == K_n:
                            # Tie all remaining bots and go to next round
                            next_round = True

                if not paused or step or next_round:
                    break

            if next_round:
                for warrior in active_warriors:
                    if warrior.task_queue:
                        print("{} ({}) ties after {} cycles.".format(warrior.name,
                                                                    warrior.author,
                                                                    cycle))
                        warrior.ties += 1
                break
        else:
            # running until max cycles: tie
            for warrior in active_warriors:
                if warrior.task_queue:
                    print("{} ({}) ties after {} cycles.".format(warrior.name,
                                                                  warrior.author,
                                                                  cycle))
                    warrior.ties += 1

        if stop_rounds:
            break

    # print final results
    print()
    print("Final results: ({} rounds)".format(round))
    print("{} {} {} {}".format("Warrior (Author)".ljust(40), "wins".rjust(5),
                              "ties".rjust(5), "losses".rjust(5)))
    for warrior in warriors:
        print("{} {} {} {}".format(("{} ({})".format(warrior.name, warrior.author)).ljust(40),
                                  str(warrior.wins).rjust(5),
                                  str(warrior.ties).rjust(5),
                                  str(warrior.losses).rjust(5)))

    if not stop_rounds and not next_round:
        # keeps display open, until quit
        paused = True
        while paused:
            for event in pygame.event.get():
                if event.type == QUIT:
                    paused = False

    # exit pygame
    pygame.quit()


```

## File: corewar\corewar\__init__.py

- Extension: .py
- Language: python
- Size: 96 bytes
- Created: 2026-01-14 15:04:49
- Modified: 2026-01-14 15:04:49

### Code

```python
from .core import Core
from .mars import MARS
from .redcode import parse, Warrior, Instruction
```

## File: corewar\docs\icws94.txt

- Extension: .txt
- Language: plaintext
- Size: 97197 bytes
- Created: 2026-01-14 15:04:49
- Modified: 2026-01-14 15:04:49

### Code

```plaintext
Annotated Draft of the Proposed 1994 Core War Standard.

Version 3.3
Annotated Draft Last Modified: November 8, 1995
Last modified by: Damien Doligez
Base draft by: Mark Durham

[Planar's intro to ver. 3.3]

This is a list of what I've changed from version 3.2:

+ Changed "pointer counter" to "program counter" in Mark's intro.
+ Changed "A-pointer" and "B-pointer" to "A-number" and "B-number" in
  Mark's intro
+ Added A-number indirect, A-number predecrement, and A-number
  postincrement to the description of addressing modes.  Changed
  "indirect", "predecrement", and "postincrement" to "B-number indirect",
  etc.
+ Clarified the fact that newlines are not considered whitespace.
+ Added the SEQ, SNE, and NOP opcodes
+ Changed a reference to "load file" into "assembly file" in section 2.3
+ Simplified the grammar entries for label_list and newline.
+ Removed the grammar entries for list, simplified those for files.
+ Stop parsing (not simply assembling) after the END.
+ Added predefined labels.
+ Added ";assert" comment convention.
+ Specified the behaviour of {DIV,MOD}.{I,F,X} when a component of the
  A-value is 0.
+ Fixed a discrepancy between the text and the sample code on the
  behavior of JMN and DJN, >>>BY CHANGING THE TEXT<<<.  The old version
  would not jump (for JMN.F and DJN.F) if either field of the target
  was zero.
+ Added SEQ as a synonym to CMP (in description and code)
+ Added SNE (in description and code)
+ Added NOP (in description and code)
+ Specified the behavior of SLT.F
+ Fixed the bug with label "noqueue" in the ARITH_DIV macro.
+ Updated the conversion tables.
+ Updated the list of new opcodes and addressing modes.

This is a list of things to do:

+ Decide on whether to remove read/write distance.
+ Add ROUNDS and PSPACE and LDP and STP.
+ Define "battle" and "rounds" in the glossary.
+ The assembler and run-time environment must agree on the value of
  predefined labels.  Make this fact explicit.
+ Add CURLINE and VERSION.
+ Decide which one takes precedence if the description and code
  disagree and write this decision explicitely in the standard.
+ Add the comparison and logical operators to the description and
  to the grammar of expressions.
+ Specify the operator precedence for expressions (if only by saying
  it's the same as in the C language).
+ Add multi-line EQUs and FOR/ROF macros.

[Stefan's intro to ver. 3.2]

The sample simulator was rewritten extensively based on suggestions by Damien
Doligez ("Planar") and on our experience implemementing the pMARS, the first
ICWS'94 simulator. Thanks to Planar and also Steven Morrell for pointing out
many omission and ambiguities in the previous revision. Other readers of
rec.games.corewar have also provided many helpful comments.

Changes incorporated since last revision:
    Text:
        - corrected various typos
        - clarified behaviour of JMN, JMZ and DJN with .F modifier
        - defined behavior for division by zero
        - incorporated EOF in grammar, eliminated "empty" expression
        - limited definition of whitespace to <space> and <tab>
        - labels are case sensitive
        - "pointer counter" -> "program counter"
        - added default modifier rules (A.2.1.1-2)
    Sample code:
        - macro'ized ADD/SUB/MUL/DIV code
        - test for division by zero
        - .AB in JMZ, JMN, DJN works now like .B; .BA like .A
        - fixed DJN.F, JMN.F

To do for next revision:
        - fix formal grammar (still flaky)
        - exclude/redefine read/write limits, add jump limit?

[Mark's intro to ver. 3.1]

The information presented here is not part of the Draft proper.  The Draft
proper immediately follows these annotations, beginning with the line
"0001 Draft of Proposed 1994 Core War Standard".  The content lines of the
Draft proper are numbered for easy reference.  The numbers may or may not
be included in the final Draft.

Internal annotations were removed to clean-up the draft for presentation to
the ICWS for comment.  These annotations which precede the draft take their
place.

Open-ended references were removed to clean-up the draft for presentation
to the ICWS for comment.  The question of the inclusion or exclusion of
various opcodes, modes, etc. has not been closed as of yet.  Such additions
or deletions should be finalized by the next draft however.

Previously speculative references were either included or removed to
clean-up the draft for presentation to the ICWS for comment.  See above.

The Load File section was rewritten to aid in the readability of load
files.  It was deemed best that Load Files be a subset of Assembly Files;
therefore Load Files should logically follow the Assembly File section.
For that reason, the two sections have been swapped.

Example MARS code is now included.  Other parts of the standard, such as
validation, remain incomplete.  The remaining incomplete sections do not
impact on the other sections of the standard and so can be completed even
after consideration of the rest of the draft by the ICWS.  Alternatively,
they could be issued as separate documents.

The MARS code is specifically designed to mirror the draft as closely as
possible.  There is a multitude of optimizations which could have been
made but were not in order that the example code could serve as a
possible clarification of obscure parts of the draft.  Do not suggest
changes to the example code which speed up processing at the expense of
mirroring the draft.

Several changes have been made with the goal of expanding the flexibility
of Core War without compromising backwards compatibility and without
seriously altering the nature of the game.  In that vein:

The modulus '%' operator was added to the Assembly File section.

Read and Write limitations with folding have been clarified.  These limits
allow the possibility of warriors essentially running in a mini-core inside
core, folding out-of-bounds access attempts back into accessible memory.
The main advantages to folding are: old-style bombers like Dwarf do not
unfairly and unknowingly spend cycles doing nothing, and movement to seek
and destroy enemy warriors is still encouraged by the limits.  The main
disadvantage is that limits which are not factors of the size of core lead
to unexpected results.  Example: a reference to address location -1 is
adjusted to M-1 when loaded into core and will not fold to R-1 and/or W-1
if R or W are not factors of M (M is size of core, R is the read limit, and
W is the write limit).  Of course, if R = W = M, then play is equivalent
to ICWS'88 without limits.


In the 5.MARS section of the draft, many of the terms such as A-operand
were used both as containers ("Writes to the A-operand") and the contents
of those containers ("Compare the A-operand to ...").  Such ambiguous terms
and references have hopefully been eradicated.

Although such eradication eliminates ambiguity, it encourages obfuscation
and/or the proliferation of terms.  A delicate balance has, perhaps, been
struck between the two.

The following are terms which are new or may be used differently than in
the past.  All terms are contents (not containers).

opcode modifier : Removes mode-specific behaviour from opcodes by
        explicitly stating whether an instruction uses just one number,
        two numbers, or a whole instruction.
A-number : Replaces A-field/A-value/A-term, etc.  A general term, not tied
        to any specific instruction.
B-number : Replaces B-field/B-value/B-term, etc.  A general term, not tied
        to any specific instruction.
current instruction : Specifically means the instruction in the instruction
        register.  Does NOT mean the instruction in core pointed to by the
        program counter.  (That instruction may have changed since the
        current instruction was copied from there).
A-instruction : Specifically means the copy of the instruction in core (at
        the time of A-operand evaluation) pointed to by the A-number.
B-instruction : Specifically means the copy of the instruction in core (at
        the time of B-operand evaluation) pointed to by the B-number.
A-value : Now refers to the object(s) (A/B-number(s) of the A-instruction
        or the A-instruction) referenced by the A-operand (as selected by
        the opcode modifier).
B-value : Now refers to the object(s) (A/B-number(s) of the B-instruction
        or the B-instruction) referenced by the B-operand (as selected by
        the opcode modifier).
B-target: The object(s) (A/B-number(s) of the instruction in core [at the
        time of opcode execution] or the instruction) pointed to by the
        B-number.


Six opcode modifiers have been added to the Draft.  Modifiers are appended
to the opcodes with a dot.  Example: "MOV.A".  The modifiers are:

.A      Instructions use and write A-numbers.
.B      Instructions use and write B-numbers.
.AB     Instructions use the A-numbers of the A-instructions and the
                B-numbers of the B-instructions and write B-numbers.
.BA     Instructions use the B-numbers of the A-instructions and the
                A-numbers of the B-instructions and write A-numbers.
.F      Instructions use both the A-numbers and the B-numbers, using and
                writing A-to-A, B-to-B.
.X      Instructions use both the A-numbers and the B-numbers, using and
                writing A-to-B, B-to-A.
.I      Instructions use and write entire instructions.

See Section 5.4 for more information (especially the examples).

There could be modifiers (other than .I) which take the modes into account,
but their utility may not warrant their inclusion.

The advantages of opcode modifiers include: greatly expanding the function
of opcodes without greatly expanding the number of opcodes, separating
opcode evaluation from operand evaluation (i.e. the behaviours of the
opcodes no longer depend on the modes), rendering moot questions about
whether ADD, SUB, etc. should use one or two fields (and if one field,
whether to use the A-field or the B-field), adding versatility to the order
of task splitting, and providing a "Skip if greater than" equivalent to
SLT.

In addition, backwards compatibility with ICWS'88 (and even ICWS'86) is
easily accomplished at the assembly level.  Any instructions with opcodes
without modifiers would be translated to the appropriate opcode.modifier
pair.  Examples:

"MOV #a, B", which only moves the A-field of the current instruction to the
B-field of the instruction pointed to by B, would be translated to
"MOV.AB #a, B".  Similarly, "MOV a, b", which moves an entire instruction
from A to B, becomes "MOV.I a, b".  Instructions which were previously
impossible, such as moving a B-field to an A-field, are now very
simple and intuitive with "MOV.BA A, B".  Another example,
"MOV.X target, target" takes the place of "XCH target", exchanging fields.
Finally, "ADD a, b" would translate to "ADD.F a, b" for ICWS'88 and
"ADD.B a, b" for ICWS'86.

There is one negative to one opcode modifier.  ".I" only really makes sense
for MOV and CMP.  It would be possible to define results for arithmetic
manipulation and ordinal comparison of opcodes and modes, but it would be
very artificial.  As an alternative, .I falls back to .F functionality (for
opcodes other than MOV and CMP) in this document.


Things which absolutely must be done before final consideration for
adoption by the ICWS:

        1. Complete incomplete sections or remove references to them
        2. Add typographic distinctions to grammars

To aid in completion of the draft, all suggested revisions of the draft
should consist of explicit remarks such as:

        Delete lines xxxx to yyyy
        Add the following after line zzzz ....
        Replace lines vvvv to wwww with ....

Please individually explain why each revision is necessary.


The maximal verbosity of the draft is intentional.  Each sentence either
presents a new item, a clarification of an item, or an old item in a new
context.  The goal is that no two reasonable people could arrive at
two different interpretations of the draft.

\start numbering
0001 Draft of Proposed 1994 Core War Standard

0002 Version 3.3
0003 Draft Last Modified: November 8, 1995
0004 Last modified by: Damien Doligez
0005 Base draft by: Mark Durham


0006 i. Contents

0007         1. Introduction
0008                 1. Purpose
0009                 2. Overview
0010                 3. Acknowledgements
0011         2. Redcode Assembly File Format
0012                 1. Purpose
0013                 2. Description
0014                 3. Grammar
0015                 4. Assembly To Object Code Conversion
0016                 5. Pseudo-instructions
0017                 6. Comment Conventions
0018                 7. Example Assembly File
0019         3. Load File Format
0020                 1. Purpose
0021                 2. Description
0022                 3. Grammar
0023                 4. Comment Conventions
0024                 5. Example Load File
0025         4. Run-time Variables
0026                 1. Purpose
0027                 2. Predefined Labels
0028                 3. Variables
0029                 4. Standard Variable Sets
0030         5. MARS
0031                 1. Purpose
0032                 2. Description
0033                 3. Address Modes
0034                         1. Immediate
0035                         2. Direct
0036                         3. A-number Indirect
0037                         4. B-number Indirect
0038                         5. A-number Predecrement Indirect
0039                         6. B-number Predecrement Indirect
0040                         7. A-number Postincrement Indirect
0041                         8. B-number Postincrement Indirect
0042                 4. Modifiers
0043                         1. A
0044                         2. B
0045                         3. AB
0046                         4. BA
0047                         5. F
0048                         6. X
0049                         7. I
0050                 5. Instruction Set
0051                          1. DAT
0052                          2. MOV
0053                          3. ADD
0054                          4. SUB
0055                          5. MUL
0056                          6. DIV
0057                          7. MOD
0058                          8. JMP
0059                          9. JMZ
0060                         10. JMN
0061                         11. DJN
0062                         12. SEQ and CMP
0063                         13. SNE
0064                         14. SLT
0065                         15. SPL
0066                         16. NOP
0067                 6. Example MARS interpreter
0068         6. Validation Suite
0069                 1. Purpose and Requirements
0070                 2. Tests
0071                         1. Assembly to Load File Test
0072                         2. MARS Tests
0073                                  1. DAT Tests
0074                                  2. MOV Tests
0075                                  3. ADD Tests
0076                                  4. SUB Tests
0077                                  5. MUL Tests
0078                                  6. DIV Tests
0079                                  7. MOD Tests
0080                                  8. JMP Tests
0081                                  9. JMZ Tests
0082                                 10. JMN Tests
0083                                 11. DJN Tests
0084                                 12. SEQ/CMP Tests
0085                                 13. SNE Tests
0086                                 14. SLT Tests
0087                                 15. SPL Tests
0088                                 16. NOP Tests
0089         7. Glossary and Index

0090         A. Differences Between Standards
0091                 1. Purpose
0092                 2. Changes
0093                         1. Assembly Files
0094                                 1. ICWS'88 conversion
0095                                 2. ICWS'86 conversion
0096                         2. Load Files
0097                         3. MARS


0098 1. Introduction

0099 1.1 Purpose
0100 This standard seeks to fully define and describe the game of Core War.

0101 1.2 Overview
0102 Core War is a game in which programs compete for control of a computer
0103 called MARS (for Memory Array Redcode Simulator).  Redcode is the name
0104 of the assembly language in which Core War programs, called warriors,
0105 are written.

0106 In order to play Core Wars, access to a Core War system is required.
0107 A Core War system at a minimum must have a MARS executive function
0108 (interpreter) and a way to load warriors into core (the MARS memory).
0109 Most systems include a Redcode assembler, either separately or as part
0110 of the loader.  Also, many systems include a graphical interface and
0111 code debugging features.  Some systems have the ability to run
0112 automated tournaments.

0113 1.3 Acknowledgements
0114 This document is the fourth standard for Core War, the first three
0115 being "Core War Guidelines" (March 1984) by D. G. Jones and
0116 A. K. Dewdney, the International Core War Society standard of 1986 -
0117 "Core Wars" (May 1986), principally authored by Graeme McRae and the
0118 "Core Wars Standard of 1988" (Summer 1988), principally authored by
0119 Thomas Gettys.  The latter two standards are often referred to as
0120 ICWS'86 and ICWS'88, respectively.

0121 People who contributed to this document (in alphabetical order):
0122         Scott W. Adkins
0123         Mark A. Durham
0124         Anders Ivner
0125         Morten Due Joergensen
0126         Paul Kline
0127         Scott Nelson
0128         Jon Newman
0129         John Perry
0130         Andy Pierce
0131         Planar
0132         Wayne Sheppard
0133         William Shubert
0134         Nandor Sieben
0135         Stefan Strack
0136         Mintardjo Wangsaw
0137         Kevin Whyte


0138 2. Redcode Assembly File Format

0139 2.1 Purpose
0140 A Redcode assembly file consists of the information necessary for a
0141 Redcode assembler to produce a load file.  A standard assembly file
0142 format allows programmers to exchange warriors in a more meaningful
0143 format than load files.  An assembly file, through the use of labels,
0144 arithmetic expressions, and macros can also greatly reduce the work
0145 necessary to produce a particular warrior while enhancing code
0146 readability.

0147 2.2 Description
0148 Each Redcode warrior consists of one or more lines of Redcode.  Each
0149 line of Redcode consists of a string of alphanumerals and special
0150 characters.  Special characters in Redcode are the addressing mode
0151 indicators for immediate '#', direct '$', A-number indirect '*',
0152 B-number indirect '@', A-number predecrement indirect '{', B-number
0153 predecrement indirect '<', A-number postincrement indirect '}', and
0154 B-number postincrement indirect '>' modes, the field separator
0155 (comma) ',', the comment indicator (semicolon) ';', the arithmetic
0156 operators for addition '+', subtraction '-', multiplication '*',
0157 division '/', and  modulus '%', and opening '(' and closing ')'
0158 parentheses for precedence grouping.

0159 A line may be blank or consist of an instruction, a
0160 pseudo-instruction, a comment, or an instruction or
0161 pseudo-instruction followed by a comment.  Each line is terminated
0162 with a newline.  All comments begin with a semicolon.  Each
0163 instruction consists of these elements in the following order: a
0164 label, an opcode, an A-operand, a comma, and a B-operand.  Each
0165 element may be preceded and/or followed by whitespace (newline is
0166 not considered whitespace).  The label is optional.  If either
0167 operand is blank, the comma may be omitted.  The operands may not
0168 be both blank.

0169 Pseudo-instructions appear just like instructions but are directives
0170 to the assembler and do not result in object code as an instruction
0171 would.  Each pseudo-instruction has a pseudo-opcode which appears
0172 where an opcode would appear in an instruction.  The format of the
0173 remainder of the pseudo-instruction depends on which pseudo-opcode is
0174 used.  For the remainder of this section (2.2) and the next (2.3),
0175 references to "opcode" include "pseudo-opcode" assembler directives.

0176 A label is any alphanumeric string other than those reserved for
0177 opcodes.  Labels are case sensitive, i.e. "start" is different from
0178 "Start".  An opcode is any of the following: DAT, MOV, ADD, SUB, MUL,
0179 DIV, MOD, JMP, JMZ, JMN, DJN, CMP, SEQ, SNE, SLT, SPL, and NOP.
0180 Opcodes may be in upper or lower case or any combination.  An opcode
0181 may be followed by a modifier.  A modifier always begins with a dot.
0182 A modifier is any of the following: .A, .B, .AB, .BA, .F, .X, or .I.
0183 Modifiers may be in upper or lower case or any combination.

0184 Each operand is blank, contains an address, or contains an addressing
0185 mode indicator and an address.  An address consists of any number of
0186 labels and numbers separated by arithmetic operators and possibly
0187 grouped with parentheses.  All elements of an address may be separated
0188 by whitespace.

0189 2.3 Grammar
0190 Tokens are separated by whitespace (space and tab) exclusive of
0191 newline characters, which are used for line termination.  End-of-file
0192 should occur only where newline could logically occur, otherwise the
0193 assembly file is invalid.

0194 In the following, 'e' is the "empty" element, meaning the token may be
0195 omitted, a caret '^' means NOT, an asterisk '*' immediately adjacent
0196 means zero or more occurrences of the previous token, and a plus '+'
0197 immediately adjacent means one or more occurrences of the previous
0198 token.  The vertical bar '|' means OR.

0199         assembly_file:
0200                 line+ EOF
0201         line:
0202                 comment | instruction
0203         comment:
0204                 ; v* newline | newline
0205         instruction:
0206                 label_list operation mode expr comment |
0207                 label_list operation mode expr , mode expr comment
0208         label_list:
0209                 label newline* label_list | e
0210         label:
0211                 alpha alphanumeral*
0212         operation:
0213                 opcode | opcode.modifier
0214         opcode:
0215                 DAT | MOV | ADD | SUB | MUL | DIV | MOD |
0216                 JMP | JMZ | JMN | DJN | CMP | SEQ | SNE |
0217                 SLT | SPL | NOP | ORG | EQU | END
0218         modifier:
0219                 A | B | AB | BA | F | X | I
0220         mode:
0221                 # | $ | * | @ | { | < | } | > | e
0222         expr:
0223                 term |
0224                 term + expr | term - expr |
0225                 term * expr | term / expr |
0226                 term % expr
0227         term:
0228                 label | number | ( expression )
0229         number:
0230                 whole_number | signed_integer
0231         signed_integer:
0232                 +whole_number | -whole_number
0233         whole_number:
0234                 numeral+
0235         alpha:
0236                 A-Z | a-z | _
0237         numeral:
0238                 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9
0239         alphanumeral:
0240                 alpha | numeral
0241         v:
0242                 ^newline
0243         newline:
0244                 LF | CR | LF CR | CR LF
0245         e:


0246 2.4 Assembly To Load File Conversion
0247 A Redcode program can be assembled into a list of MARS instructions.
0248 (When assembled to a file instead of directly to core, the list is
0249 called a load file.  See Section 3).  Each Redcode instruction
0250 assembles into a MARS instruction of five fields: an opcode.modifier
0251 field, the A-mode field, the A-address field, the B-mode field, and
0252 the B-address field.  A missing (null or blank) mode assembles as '$'
0253 does.

0254 If no modifier is present in the assembly instruction, the appropriate
0255 modifier is appended to the opcode.  The appropriate modifier depends
0256 upon the opcode, the modes, and which standard (ICWS'86 or ICWS'88) to
0257 consider (ICWS'88 by default).  See Appendix A for the appropriate
0258 translations.

0259 The address field values are derived from the numbers, labels, and
0260 arithmetic operators contained in the addresses.  Labels are
0261 converted to an address relative to the current instruction.  Then
0262 the arithmetic operations are carried out according to the
0263 appropriate operator and parenthetical precedence to determine the
0264 final value.  If there is only one operand associated with a DAT
0265 instruction, this operand is assembled into the B-mode and B-address
0266 fields, while #0 is assembled into the A-mode and A-address fields.
0267 For all other instructions with only one operand, this operand is
0268 assembled into the A-mode and A-address fields and #0 is assembled
0269 into the B-mode and B-address fields.

0270 2.5 Pseudo-instructions
0271 Pseudo-opcodes are "ORG", "EQU", and "END".

0272 "ORG" ("ORiGin") is a way for the assembly file to indicate the
0273 logical origin of the warrior.  The A-operand contains an offset to
0274 the logical first instruction.  Thus "ORG 0" means execution should
0275 start with the first instruction (the default) whereas "ORG 6" means
0276 execution should start with the seventh instruction. Although multiple
0277 ORG instructions are of no additional benefit to the programmer, they
0278 are allowed. When there is more than one ORG instruction in a file,
0279 the last ORG instruction encountered will be the one that takes
0280 effect.

0281 "EQU" ("EQUate") is a simple text substitution utility.  Instructions
0282 of the form "label EQU text" will replace all occurrences of "label"
0283 with the (probably longer and more complicated) "text" before any
0284 actual assembly takes place on the file.  Some labels are predefined
0285 with the value of run-time variables as if they were defined with
0286 EQU at the start of the program (see section 4.2 for the list of
0287 predefined labels).

0288 "END" indicates the logical end of the assembly file.  If END has an
0289 A-operand, then the A-operand indicates the logical origin of the
0290 warrior in the same manner as ORG does.  The rest of the file (after
0291 the end of the line containing END) is ignored.


0292 2.6 Comment Conventions
0293 ";redcode<switch>" as a first line identifies the file as a Redcode
0294 assembly file.  The "<switch>" is optional and implementation
0295 dependent.

0296 ";strategy <text>" indicates a comment for "public" consumption.

0297 ";name <program name>", ";author <name of author(s)>",
0298 ";version <version number>", and ";date <date of last revision>"
0299 offer uniform ways of presenting this information.

0300 ";kill <program name>" is for removing warriors from ongoing
0301 tournaments.  If no <program name> is supplied, all of the author's
0302 previous submissions will be removed.

0303 ";assert <expression>" will evaluate the expression and trigger
0304 an error if it is 0.  In conjunction with predefined labels (see
0305 section 4.2), this provides a way of specifying the conditions under
0306 which a warrior is supposed to run.


0307 2.7 Example Assembly File

0308 ;redcode

0309 ;name          Dwarf
0310 ;author        A. K. Dewdney
0311 ;version       94.1
0312 ;date          April 29, 1993

0313 ;strategy      Bombs every fourth instruction.
0314 ;assert        CORESIZE % 4 == 0

0315         ORG     start              ; Indicates the instruction with
0316                                    ; the label "start" should be the
0317                                    ; first to execute.

0318 step    EQU      4                 ; Replaces all occurrences of "step"
0319                                    ; with the character "4".

0320 target  DAT.F   #0,     #0         ; Pointer to target instruction.
0321 start   ADD.AB  #step,   target    ; Increments pointer by step.
0322         MOV.AB  #0,     @target    ; Bombs target instruction.
0323         JMP.A    start             ; Same as JMP.A -2.  Loops back to
0324                                    ; the instruction labelled "start".
0325         END


0326 3. Load File Format

0327 3.1 Purpose
0328 A load file represents the minimum amount of information necessary for
0329 a warrior to execute properly and is presented in a very simple format
0330 which is a subset of the assembly file format presented in Section 2.
0331 A standard load file format allows programmers to choose assemblers
0332 and MARS programs separately and to verify assembler performance and
0333 MARS performance separately.  Not all Core War systems will necessarily
0334 write load files (for example, those which assemble directly to core),
0335 but all systems should support reading load files.

0336 3.2 Description

0337 Each load file will consist of one or more lines of MARS
0338 instructions or comments.  Each line is terminated with a newline.
0339 All comments start with with a semicolon.  Each MARS instruction
0340 consists of five fields: an opcode.modifier pair, an A-mode, an
0341 A-field, a B-mode, and a B-field.  The A-mode is separated from the
0342 opcode.modifier pair by whitespace and the B-mode is separated from
0343 the A-field by a comma and additional whitespace.  Each MARS
0344 instruction may be followed by extraneous information, which is
0345 ignored.  Note that the instruction format for load files is more
0346 rigid than for assembly files to simplify parsing. No blank modes or
0347 operands are allowed.


0348 3.3 Grammar
0349 Tokens are separated by whitespace (non-marking characters such as
0350 SPACE and TAB) exclusive of newline characters, which are used for
0351 line termination.  End-of-file should occur only where newline could
0352 logically occur, otherwise the load file is invalid.

0353         load_file:
0354                 line+ EOF
0355         line:
0356                 comment | instruction
0357         comment:
0358                 ; v* newline | newline
0359         instruction:
0360                 opcode.modifier mode number , mode number comment
0361         opcode:
0362                 DAT | MOV | ADD | SUB | MUL | DIV | MOD |
0363                 JMP | JMZ | JMN | DJN | CMP | SEQ | SNE |
0364                 SLT | SPL | NOP | ORG
0365         modifier:
0366                 A | B | AB | BA | F | X | I
0367         mode:
0368                 # | $ | @ | * | < | { | > | }
0369         number:
0370                 whole_number | signed_integer
0371         signed_integer:
0372                 +whole_number | -whole_number
0373         whole_number:
0374                 numeral+
0375         numeral:
0376                 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9
0377         v:
0378                 ^newline
0379         newline:
0380            LF | CR | LF CR | CR LF


0381 3.4 Comment Conventions
0382 Comment conventions for load files are the same as for assembly files.
0383 Of particular note are the "; name <program name>" and "; author
0384 <author(s)>" comments.  These comments provide a more suitable
0385 identification of programs to the MARS than "Warrior #1", "Warrior #2",
0386 etc.  It also allows for less cryptic identification than by filename.


0387 3.5 Example Load File
0388 ;redcode

0389 ;name          Dwarf
0390 ;author        A. K. Dewdney
0391 ;version       94.1
0392 ;date          April 29, 1993

0393 ;strategy      Bombs every fourth instruction.
0394 ;assert        CORESIZE % 4 == 0

0395 ORG     1          ; Indicates execution begins with the second
0396                    ; instruction (ORG is not actually loaded, and is
0397                    ; therefore not counted as an instruction).

0398 DAT.F   #0, #0     ; Pointer to target instruction.
0399 ADD.AB  #4, $-1    ; Increments pointer by step.
0400 MOV.AB  #0, @-2    ; Bombs target instruction.
0401 JMP.A   $-2, #0    ; Loops back two instructions.


0402 4. Run-time Variables

0403 4.1 Purpose
0404 This section describes those variables which are determined just prior
0405 to running a battle by the person running the battle.  It also
0406 enumerates some of the standardized sets of variables used for
0407 tournaments.

0408 4.2 Predefined Labels
0409 Most of the run-time variables are available to the programmer as
0410 predefined labels.  The purpose of these labels is twofold: first,
0411 to parameterize the warriors with the characteristics of their
0412 run-time environment; second, to check (with the ";assert" comment)
0413 that the warrior is run in an environment that makes sense for it.

0414 The next section gives a list of the run-time variables.  When
0415 a predefined label takes the value of the variable, the label is
0416 given between parentheses after the name of the variable.

0417 4.2 Variables
0418 Run-time variables consist of the following:

0419 Core Size: (CORESIZE)
0420         Core size is the number of instructions which make up core
0421         during the battle.

0422 Cycles Before Tie: (MAXCYCLES)
0423         In each cycle, one instruction from each warrior is executed.
0424         This variable determines how many cycles without a winner
0425         should be executed before declaring a tie.

0426 Initial Instruction:
0427         The initial instruction is that instruction which is preloaded
0428         into core prior to loading warriors.  In addition to loading
0429         an instruction such as "DAT #0, #0" into all of core, the
0430         initial instruction could be set to "NONE", meaning core should
0431         not be cleared between battles, or "RANDOM", meaning core
0432         instructions are filled with randomly generated instructions.

0433 Instruction Limit: (MAXLENGTH)
0434         The maximum number of instructions allowed per load file.

0435 Maximum Number of Tasks: (MAXPROCESSES)
0436         Each warrior can spawn multiple additional tasks.  This
0437         variable sets the maximum number of tasks allowed per warrior.
0438         In other words, this is the size of each warrior's task queue.

0439 Minimum Separation: (MINDISTANCE)
0440         The minimum number of instructions from the first instruction
0441         of one warrior to the first instruction of the next warrior.

0442 Read Distance:
0443         This is the range available for warriors to read information
0444         from core.  Attempts to read outside the limits of this range
0445         result in reading within the local readable range.  The range
0446         is centered on the current instruction.  Thus, a range of
0447         500 limits reading to offsets of (-249 -> +250) from the
0448         currently executing instruction.  The read limit can therefore
0449         be considered a mini-core within core.  An attempt to read
0450         location PC+251 reads location PC-249 instead.  An attempt to
0451         read location PC+500 reads location PC instead.

0452         Read distance must be a factor of core size, otherwise the
0453         above defined behaviour is not guaranteed.

0454 Separation:
0455         The number of instructions from the first instruction of one
0456         warrior to the first instruction of the next warrior.
0457         Separation can be set to "RANDOM", meaning separations will be
0458         chosen randomly from those larger than the minimum separation.

0459 Warriors:
0460         The initial number of warriors to battle simultaneously in
0461         core.

0462 Write Distance:
0463         This is the range available for warriors to write information
0464         to core.  Attempts to write outside the limits of this range
0465         result in writing within the local writable range.  The range
0466         is centered on the current instruction.  Thus, a range of 500
0467         limits writing to offsets of (-249 -> +250) from the
0468         currently executing instruction.  The write limit can
0469         therefore be considered a mini-core within core.  An attempt
0470         to write location PC+251 writes to location PC-249 instead.
0471         An attempt to write to location PC+500 writes to location PC
0472         instead.

0473         Write distance must be a factor of core size, otherwise the
0474         above defined behaviour is not guaranteed.


0475 4.3 Standard Variable Sets
0476 ICWS86:
0477         Core Size:                      8192
0478         Cycles Before Tie:              100000
0479         Initial Instruction:            DAT.F #0, #0
0480         Instruction Limit:              300
0481         Maximum Number of Tasks:        64
0482         Minimum Separation:             300
0483         Read Distance:                  8192
0484         Separation:                     RANDOM
0485         Warriors:                       2
0486         Write Distance:                 8192

0487 KOTH:
0488         Core Size:                      8000
0489         Cycles Before Tie:              80000
0490         Initial Instruction:            DAT.F $0, $0
0491         Instruction Limit:              100
0492         Maximum Number of Tasks:        8000
0493         Minimum Separation:             100
0494         Read Distance:                  8000
0495         Separation:                     RANDOM
0496         Warriors:                       2
0497         Write Distance:                 8000


0498 5. MARS

0499 5.1 Purpose
0500 The Memory Array Redcode Simulator (MARS) is the computer in which
0501 Core War warriors do combat.

0502 5.2 Description
0503 A minimally-complete MARS consists of a core, a loader, task queues,
0504 the MARS executive function, and a way to present the final results of
0505 a battle.  Additionally, many MARS provide a "real-time" battle
0506 display and various debugging tools.

0507 The core consists of a cyclic list (0, 1, 2, ..., M-2, M-1, 0, 1, ...)
0508 of M MARS instructions.  The integer M is referred to as "core size".
0509 All operations are performed modulo M.  Core initialization (the
0510 initial instructions placed in core before loading warriors) is a
0511 run-time variable (see Section 4).

0512 The loader loads warriors into core, converting each negative field
0513 value N to the positive field value P such that 0 <= P < M and P = kM
0514 + N where k is a positive integer (P = N modulo M).  Each field value
0515 G greater than or equal to M is converted to the field values L such
0516 that 0 <= L < M and L = kM + G where k is a negative integer (L = G
0517 modulo M).  The loader also initializes each warrior's task queue with
0518 the appropriate task pointer.

0519 There is a task queue for each warrior loaded into core.  Each task
0520 queue can hold a limited number of task pointers.  The "task limit"
0521 (number of tasks an individual warrior's task queue can hold) is a
0522 run-time variable.  The task queues are FIFOs (First In, First Out).

0523 Each warrior consists of one task initially.  Subsequent tasks are
0524 added to the warrior's task queue using the SPL instruction. Attempted
0525 execution of a DAT instruction by a task effectively removes that task
0526 from the warrior's task queue.

0527 Warriors execute for a specified number of cycles ("time limit", see
0528 Section 4) or until only one warrior is still executing, whichever
0529 occurs first.  Each cycle, one instruction from each warrior is
0530 executed.  The instruction to execute is the instruction pointed to by
0531 the next task pointer in the warrior's task queue.  A warrior is no
0532 longer executing when its task queue is empty.

0533 The following expressions are used in describing the MARS executive
0534 function's operation.

0535 General Definitions:
0536    An instruction consists of an opcode, a modifier, an A-operand,
0537            and a B-operand.
0538    An A-operand consists of an A-mode and an A-number.
0539    An A-mode is the addressing mode of an A-operand.
0540    An A-number is an integer between 0 and M-1, inclusive.
0541    A B-operand consists of a B-mode and a B-number.
0542    A B-mode is the addressing mode of a B-operand.
0543    A B-number is an integer between 0 and M-1, inclusive.

0544 Specific Definitions:
0545    The program counter (PC) is the pointer to the location in core of
0546            the instruction fetched from core to execute.
0547    The current instruction is the instruction in the instruction
0548            register, as copied (prior to execution) from the PC
0549            location of core.
0550    The A-pointer points to the instruction the A-operand of the
0551            current instruction references in core.
0552    The A-instruction is a copy of the instruction the A-pointer
0553            points to in core (as it was during operand evaluation).
0554    The A-value is the A-number and/or the B-number of the
0555            A-instruction or the A-instruction itself, whichever are/is
0556            selected by the opcode modifier.
0557    The B-pointer points to the instruction the B-operand of the
0558            current instruction references in core.
0559    The B-instruction is a copy of the instruction the B-pointer
0560            points to in core (as it was during operand evaluation).
0561    The B-value is the A-number and/or the B-number of the
0562            B-instruction or the B-instruction itself, whichever are/is
0563            selected by the opcode modifier.
0564    The B-target is the A-number and/or the B-number of the instruction
0565            pointed to by the B-pointer or the instruction itself,
0566            whichever are/is selected by the opcode modifier.

0567 All MARS instructions are executed following the same procedure:
0568 1. The currently executing warrior's current task pointer is
0569    extracted from the warrior's task queue and assigned to the
0570    program counter.
0571 2. The corresponding instruction is fetched from core and stored in
0572    the instruction register as the current instruction.
0573 3. The A-operand of the current instruction is evaluated.
0574 4. The results of A-operand evaluation, the A-pointer and the
0575    A-instruction, are stored in the appropriate registers.
0576 5. The B-operand of the current instruction is evaluated.
0577 6. The results of B-operand evaluation, the B-pointer and the
0578    B-instruction, are stored in the appropriate registers.
0579 7. Operations appropriate to the opcode.modifier pair in the
0580    instruction register are executed.  With the exception of DAT
0581    instructions, all operations queue an updated task pointer.
0582    (How the task pointer is updated and when it is queued depend on
0583    instruction execution).

0584 All pointers are PC-relative, indicating the offset from the source of
0585 the current instruction to the desired location.  All arithmetic is to
0586 be done modulo M, with negative values converted in the same manner as
0587 during loading as discussed above (P = M + N).  Additionally, all
0588 reads of core are done modulo the read limit (R) and all writes of
0589 core are done modulo the write limit (W).  Read offsets O greater than
0590 R/2 from the current instruction are converted to backwards offsets of
0591 O = O - R.  A comparable conversion occurs for write offsets greater
0592 than W/2.


0593 5.3 Address Modes

0594 5.3.1 Immediate
0595 An immediate mode operand merely serves as storage for data.  An
0596 immediate A/B-mode in the current instruction sets the A/B-pointer to
0597 zero.

0598 5.3.2 Direct
0599 A direct mode operand indicates the offset from the program counter.
0600 A direct A/B-mode in the current instruction means the A/B-pointer is
0601 a copy of the offset, the A/B-number of the current instruction.

0602 5.3.3 A-number Indirect
0603 An A-number indirect mode operand indicates the primary offset
0604 (relative to the program counter) to the secondary offset (relative to
0605 the location of the instruction in which the secondary offset is
0606 contained).  An A-number indirect A/B-mode indicates that the
0607 A/B-pointer is the sum of the A/B-number of the current instruction
0608 (the primary offset) and the A-number of the instruction pointed to by
0609 the A/B-number of the current instruction (the secondary offset).

0610 5.3.4 B-number Indirect
0611 A B-number indirect mode operand indicates the primary offset
0612 (relative to the program counter) to the secondary offset (relative to
0613 the location of the instruction in which the secondary offset is
0614 contained).  A B-number indirect A/B-mode indicates that the
0615 A/B-pointer is the sum of the A/B-number of the current instruction
0616 (the primary offset) and the B-number of the instruction pointed to by
0617 the A/B-number of the current instruction (the secondary offset).

0618 5.3.5 A-number Predecrement Indirect
0619 An A-number predecrement indirect mode operand indicates the primary
0620 offset (relative to the program counter) to the secondary offset
0621 (relative to the location of the instruction in which the secondary
0622 offset is contained) which is decremented prior to use.  An A-number
0623 predecrement indirect A/B-mode indicates that the A/B-pointer is the
0624 sum of the A/B-number of the current instruction (the primary offset)
0625 and the decremented A-number of the instruction pointed to by the
0626 A/B-number of the current instruction (the secondary offset).

0627 5.3.6 B-number Predecrement Indirect
0628 A B-number predecrement indirect mode operand indicates the primary
0629 offset (relative to the program counter) to the secondary offset
0630 (relative to the location of the instruction in which the secondary
0631 offset is contained) which is decremented prior to use.  A B-number
0632 predecrement indirect A/B-mode indicates that the A/B-pointer is the
0633 sum of the A/B-number of the current instruction (the primary offset)
0634 and the decremented B-number of the instruction pointed to by the
0635 A/B-number of the current instruction (the secondary offset).

0636 5.3.7 A-number Postincrement Indirect
0637 An A-number postincrement indirect mode operand indicates the primary
0638 offset (relative to the program counter) to the secondary offset
0639 (relative to the location of the instruction in which the secondary
0640 offset is contained) which is incremented after the results of the
0641 operand evaluation are stored.  An A-number postincrement indirect
0642 A/B-mode indicates that the A/B-pointer is the sum of the A/B-number of
0643 the current instruction (the primary offset) and the A-number of the
0644 instruction pointed to by the A/B-number of the current instruction
0645 (the secondary offset).  The A-number of the instruction pointed to by
0646 the A/B-number of the current instruction is incremented after the
0647 A/B-instruction is stored, but before the B-operand is evaluated (for
0648 A-number postincrement indirect A-mode), or the operation is executed
0649 (for A-number postincrement indirect B-mode).

0650 5.3.8 B-number Postincrement Indirect
0651 A B-number postincrement indirect mode operand indicates the primary
0652 offset (relative to the program counter) to the secondary offset
0653 (relative to the location of the instruction in which the secondary
0654 offset is contained) which is incremented after the results of the
0655 operand evaluation are stored.  A B-number postincrement indirect
0656 A/B-mode indicates that the A/B-pointer is the sum of the A/B-number of
0657 the current instruction (the primary offset) and the B-number of the
0658 instruction pointed to by the A/B-number of the current instruction
0659 (the secondary offset).  The B-number of the instruction pointed to by
0660 the A/B-number of the current instruction is incremented after the
0661 A/B-instruction is stored, but before the B-operand is evaluated (for
0662 B-number postincrement indirect A-mode), or the operation is executed
0663 (for B-number postincrement indirect B-mode).


0664 5.4 Modifiers

0665 5.4.1 A
0666 Instruction execution proceeds with the A-value set to the A-number of
0667 the A-instruction and the B-value set to the A-number of the
0668 B-instruction.  A write to core replaces the A-number of the
0669 instruction pointed to by the B-pointer.

0670 For example, a CMP.A instruction would compare the A-number of the
0671 A-instruction with the A-number of the B-instruction.  A MOV.A
0672 instruction would replace the A-number of the instruction pointed to
0673 by the B-pointer with the A-number of the A-instruction.

0674 5.4.2 B
0675 Instruction execution proceeds with the A-value set to the B-number of
0676 the A-instruction and the B-value set to the B-number of the
0677 B-instruction.  A write to core replaces the B-number of the
0678 instruction pointed to by the B-pointer.

0679 For example, a CMP.B instruction would compare the B-number of the
0680 A-instruction with the B-number of the B-instruction.  A MOV.B
0681 instruction would replace the B-number of the instruction pointed to
0682 by the B-pointer with the B-number of the A-instruction.

0683 5.4.3 AB
0684 Instruction execution proceeds with the A-value set to the A-number of
0685 the A-instruction and the B-value set to the B-number of the
0686 B-instruction.  A write to core replaces the B-number of the
0687 instruction pointed to by the B-pointer.

0688 For example, a CMP.AB instruction would compare the A-number of the
0689 A-instruction with the B-number of the B-instruction.  A MOV.AB
0690 instruction would replace the B-number of the instruction pointed to
0691 by the B-pointer with the A-number of the A-instruction.

0692 5.4.4 BA
0693 Instruction execution proceeds with the A-value set to the B-number of
0694 the A-instruction and the B-value set to the A-number of the
0695 B-instruction.  A write to core replaces the A-number of the
0696 instruction pointed to by the B-pointer.

0697 For example, a CMP.BA instruction would compare the B-number of the
0698 A-instruction with the A-number of the B-instruction.  A MOV.BA
0699 instruction would replace the A-number of the instruction pointed to
0700 by the B-pointer with the B-number of the A-instruction.

0701 5.4.5 F
0702 Instruction execution proceeds with the A-value set to both the
0703 A-number and B-number of the A-instruction (in that order) and the
0704 B-value set to both the A-number and B-number of the B-instruction
0705 (also in that order).  A write to core replaces both the A-number and
0706 the B-number of the instruction pointed to by the B-pointer (in that
0707 order).

0708 For example, a CMP.F instruction would compare the A-number of the
0709 A-instruction to the A-number of the B-instruction and the B-number of
0710 the A-instruction to B-number of the B-instruction.  A MOV.F
0711 instruction would replace the A-number of the instruction pointed to by
0712 the B-pointer with the A-number of the A-instruction and would also
0713 replace the B-number of the instruction pointed to by the B-pointer
0714 with the B-number of the A-instruction.

0715 5.4.6 X
0716 Instruction execution proceeds with the A-value set to both the
0717 A-number and B-number of the A-instruction (in that order) and the
0718 B-value set to both the B-number and A-number of the B-instruction
0719 (in that order).  A write to to core replaces both the B-number and
0720 the A-number of the instruction pointed to by the B-pointer (in that
0721 order).

0722 For example, a CMP.X instruction would compare the A-number of the
0723 A-instruction to the B-number of the B-instruction and the B-number of the
0724 A-instruction to A-number of the B-instruction.  A MOV.X instruction
0725 would replace the B-number of the instruction pointed to by the
0726 B-pointer with the A-number of the A-instruction and would also replace
0727 the A-number of the instruction pointed to by the B-pointer with the
0728 B-number of the A-instruction.

0729 5.4.7 I
0730 Instruction execution proceeds with the A-value set to the
0731 A-instruction and the B-value set to the B-instruction.  A write to
0732 core replaces the entire instruction pointed to by the B-pointer.

0733 For example, a CMP.I instruction would compare the A-instruction to
0734 the B-instruction.  A MOV.I instruction would replace the instruction
0735 pointed to by the B-pointer with the A-instruction.


0736 5.5 Instruction Set

0737 5.5.1 DAT
0738 No additional processing takes place.  This effectively removes the
0739 current task from the current warrior's task queue.

0740 5.5.2 MOV
0741 Move replaces the B-target with the A-value and queues the next
0742 instruction (PC + 1).

0743 5.5.3 ADD
0744 ADD replaces the B-target with the sum of the A-value and the B-value
0745 (A-value + B-value) and queues the next instruction (PC + 1).  ADD.I
0746 functions as ADD.F would.

0747 5.5.4 SUB
0748 SUB replaces the B-target with the difference of the B-value and the
0749 A-value (B-value - A-value) and queues the next instruction (PC + 1).
0750 SUB.I functions as SUB.F would.

0751 5.5.5 MUL
0752 MUL replaces the B-target with the product of the A-value and the
0753 B-value (A-value * B-value) and queues the next instruction (PC + 1).
0754 MUL.I functions as MUL.F would.

0755 5.5.6 DIV
0756 DIV replaces the B-target with the integral result of dividing the
0757 B-value by the A-value (B-value / A-value) and queues the next
0758 instruction (PC + 1).  DIV.I functions as DIV.F would. If the
0759 A-value is zero, the B-value is unchanged and the current task is
0760 removed from the warrior's task queue.  DIV.I, DIV.F, and DIV.X
0761 operate on pairs of operands.  If either component of the A-value
0762 is zero, the corresponding component of the B-value is unchanged
0763 (the other component is divided normally), and the current task is
0764 removed from the warrior queue.

0765 5.5.7 MOD
0766 MOD replaces the B-target with the integral remainder of dividing the
0767 B-value by the A-value (B-value % A-value) and queues the next
0768 instruction (PC + 1).  MOD.I functions as MOD.F would. If the
0769 A-value is zero, the B-value is unchanged and the current task is
0770 removed from the warrior's task queue.  MOD.I, MOD.F, and MOD.X
0771 operate on pairs of operands.  If either component of the A-value
0772 is zero, the corresponding component of the B-value is unchanged
0773 (the other component is divided normally), and the current task is
0774 removed from the warrior queue.

0775 5.5.8 JMP
0776 JMP queues the sum of the program counter and the A-pointer.

0777 5.5.9 JMZ
0778 JMZ tests the B-value to determine if it is zero.  If the B-value is
0779 zero, the sum of the program counter and the A-pointer is queued.
0780 Otherwise, the next instruction is queued (PC + 1).  JMZ.I functions
0781 as JMZ.F would, i.e. it jumps if both the A-number and the B-number
0782 of the B-instruction are zero.

0783 5.5.10 JMN
0784 JMN tests the B-value to determine if it is zero.  If the B-value is
0785 not zero, the sum of the program counter and the A-pointer is queued.
0786 Otherwise, the next instruction is queued (PC + 1).  JMN.I functions
0787 as JMN.F would, i.e. it jumps if the A-number or the B-number of the
0788 B-instruction (or both) is non-zero. This is the negation of the
0789 condition for JMZ.F.

0790 5.5.11 DJN
0791 DJN decrements the B-value and the B-target, then tests the B-value
0792 to determine if it is zero.  If the decremented B-value is not zero,
0793 the sum of the program counter and the A-pointer is queued.
0794 Otherwise, the next instruction is queued (PC + 1).  DJN.I functions
0795 as DJN.F would, i.e. it decrements both both A/B-numbers of the B-value
0796 and the B-target, and jumps if one (or both) of the A/B-numbers of the
0797 B-value is non-zero.

0798 5.5.12 SEQ and CMP
0799 SEQ and CMP are synonymous opcodes.  SEQ is provided as an
0800 easy-to-remember mnemonic, and CMP is provided for backward
0801 compatibility.  They are completely equivalent.  SEQ (or CMP) compares
0802 the A-value to the B-value.  If the result of the comparison is equal,
0803 the instruction after the next instruction (PC + 2) is queued (skipping
0804 the next instruction).  Otherwise, the next instruction is queued
0805 (PC + 1).

0806 5.5.13 SNE
0807 SNE compares the A-value to the B-value.  If the result of the
0808 comparison is not equal, the instruction after the next instruction
0809 (PC + 2) is queued (skipping the next instruction).  Otherwise, the
0810 next instruction is queued (PC + 1).

0811 5.5.14 SLT
0812 SLT compares the A-value to the B-value.  If the A-value is less than
0813 the B-value, the instruction after the next instruction (PC + 2) is
0814 queued (skipping the next instruction).  Otherwise, the next
0815 instruction is queued (PC + 1).  SLT.I functions as SLT.F would, i.e.
0816 the next instruction is skipped only if each of the A/B-numbers of the
0817 A-value is less than its B-value counterpart.

0818 5.5.15 SPL
0819 SPL queues the next instruction (PC + 1) and then queues the sum of
0820 the program counter and the A-pointer. If the queue is full, only the
0821 next instruction is queued.

0822 5.5.16 NOP
0823 NOP queues the next instruction (PC + 1).


0824 5.6 Example MARS Interpreter

0825 /************************************/
0826 /*                                  */
0827 /*            EMI94.c               */
0828 /*                                  */
0829 /* Execute MARS Instruction ala     */
0830 /* ICWS'94 Draft Standard.          */
0831 /*                                  */
0832 /* Last Update: November 8, 1995    */
0833 /*                                  */
0834 /************************************/

0835 /* This ANSI C function is the benchmark MARS instruction   */
0836 /* interpreter for the ICWS'94 Draft Standard.              */


0837 /* The design philosophy of this function is to mirror the  */
0838 /* standard as closely as possible, illuminate the meaning  */
0839 /* of the standard, and provide the definitive answers to   */
0840 /* questions of the "well, does the standard mean this or   */
0841 /* that?" variety.  Although other, different implemen-     */
0842 /* tations are definitely possible and encouraged; those    */
0843 /* implementations should produce the same results as this  */
0844 /* one does.                                                */


0845 /* The function returns the state of the system.  What the  */
0846 /* main program does with this information is not defined   */
0847 /* by the standard.                                         */

0848 enum SystemState {
0849    UNDEFINED,
0850    SUCCESS
0851 };


0852 /* Any number of warriors may be executing in core at one   */
0853 /* time, depending on the run-time variable set and how     */
0854 /* many warriors have failed during execution.  For this    */
0855 /* implementation, warriors are identified by the order in  */
0856 /* which they were loaded into core.                        */

0857 typedef unsigned int Warrior;


0858 /* An Address in Core War can be any number from 0 to the   */
0859 /* size of core minus one, relative to the current          */
0860 /* instruction.  In this implementation, core is an array   */
0861 /* of instructions; therefore any variable types which      */
0862 /* contain an Address can be considered to be of type       */
0863 /* unsigned int.  One caveat: for the purposes of this      */
0864 /* standard, unsigned int must be considered to have no     */
0865 /* upper limit.  Depending on the size of core, it may be   */
0866 /* necessary to take precautions against overflow.          */

0867 typedef unsigned int Address;


0868 /* The FIFO task queues and supporting functions are not    */
0869 /* presented.   The function Queue() attempts to add a task */
0870 /* pointer to the back of the currently executing warrior's */
0871 /* task queue.  No special actions are to be taken if       */
0872 /* Queue() is unsuccessful, which it will be if the warrior */
0873 /* has already reached the task limit (maximum allowable    */
0874 /* number of tasks).                                        */

0875 extern void Queue(
0876    Warrior  W,
0877    Address  TaskPointer
0878 );


0879 /* There is one support function used to limit the range of */
0880 /* reading from Core and writing to Core relative to the    */
0881 /* current instruction.  Behaviour is as expected (a small  */
0882 /* core within Core) only if the limits are factors of the  */
0883 /* size of Core.                                            */

0884 static Address Fold(
0885    Address  pointer,    /* The pointer to fold into the desired range.  */
0886    Address  limit,      /* The range limit.                             */
0887    Address  M           /* The size of Core.                            */
0888 ) {
0889    Address  result;

0890    result = pointer % limit;
0891    if ( result > (limit/2) ) {
0892       result += M - limit;
0893    };
0894    return(result);
0895 }


0896 /* Instructions are the principle data type.  Core is an    */
0897 /* array of instructions, and there are three instruction   */
0898 /* registers used by the MARS executive.                    */

0899 enum Opcode {
0900    DAT,
0901    MOV,
0902    ADD,
0903    SUB,
0904    MUL,
0905    DIV,
0906    MOD,
0907    JMP,
0908    JMZ,
0909    JMN,
0910    DJN,
0911    CMP, /* aka SEQ */
0912    SNE,
0913    SLT,
0914    SPL,
0915    NOP,
0916 };

0917 enum Modifier {
0918    A,
0919    B,
0920    AB,
0921    BA,
0922    F,
0923    X,
0924    I
0925 };

0926 enum Mode {
0927    IMMEDIATE,
0928    DIRECT,
0929    A_INDIRECT,
0930    B_INDIRECT,
0931    A_DECREMENT,
0932    B_DECREMENT,
0933    A_INCREMENT,
0934    B_INCREMENT,
0935 };

0936 typedef struct Instruction {
0937    enum Opcode    Opcode;
0938    enum Modifier  Modifier;
0939    enum Mode      AMode;
0940    Address        ANumber;
0941    enum Mode      BMode;
0942    Address        BNumber;
0943 } Instruction;


0944 /* The function is passed which warrior is currently        */
0945 /* executing, the address of the warrior's current task's   */
0946 /* current instruction, a pointer to the Core, the size of  */
0947 /* the Core, and the read and write limits.  It returns the */
0948 /* system's state after attempting instruction execution.   */

0949 enum SystemState EMI94(

0950 /* W indicates which warrior's code is executing.           */

0951    Warrior  W,

0952 /* PC is the address of this warrior's current task's       */
0953 /* current instruction.                                     */

0954    Address  PC,

0955 /* Core is just an array of Instructions.  Core has been    */
0956 /* initialized and the warriors have been loaded before     */
0957 /* calling this function.                                   */

0958    Instruction Core[],

0959 /* M is the size of Core.                                   */

0960    Address     M,

0961 /* ReadLimit is the limitation on read distances.           */

0962    Address     ReadLimit,

0963 /* WriteLimit is the limitation on write distances.         */

0964    Address     WriteLimit


0965 ) {


0966 /* This MARS stores the currently executing instruction in  */
0967 /* the instruction register IR.                             */

0968    Instruction IR;

0969 /* This MARS stores the instruction referenced by the       */
0970 /* A-operand in the instruction register IRA.               */

0971    Instruction IRA;

0972 /* This MARS stores the instruction referenced by the       */
0973 /* B-operand in the instruction Register IRB.               */

0974    Instruction IRB;

0975 /* All four of the following pointers are PC-relative       */
0976 /* (relative to the Program Counter).  Actual access of     */
0977 /* core must add-in the Program Counter (mod core size).    */

0978 /* The offset to the instruction referred to by the         */
0979 /* A-operand for reading is Read Pointer A (RPA).           */

0980    Address     RPA;

0981 /* The offset to the instruction referred to by the         */
0982 /* A-operand for writing is Write Pointer A (WPA).          */

0983    Address     WPA;

0984 /* The offset to the instruction referred to by the         */
0985 /* B-operand for reading is Read Pointer B (RPB).           */

0986    Address     RPB;

0987 /* The offset to the instruction referred to by the         */
0988 /* A-operand for writing is Write Pointer B (WPB).          */

0989    Address     WPB;

0990 /* Post-increment operands need to keep track of which      */
0991 /* instruction to increment.                                */

0992    Address     PIP;

0993 /* Before execution begins, the current instruction is      */
0994 /* copied into the Instruction Register.                    */

0995    IR = Core[PC];


0996 /* Next, the A-operand is completely evaluated.             */

0997 /* For instructions with an Immediate A-mode, the Pointer A */
0998 /* points to the source of the current instruction.         */

0999    if (IR.AMode == IMMEDIATE) {
1000       RPA = WPA = 0;
1001    } else {

1002 /* For instructions with a Direct A-mode, the Pointer A     */
1003 /* points to the instruction IR.ANumber away, relative to   */
1004 /* the Program Counter.                                     */
1005 /* Note that implementing Core as an array necessitates     */
1006 /* doing all Address arithmetic modulus the size of Core.   */

1007       RPA = Fold(IR.ANumber, ReadLimit, M);
1008       WPA = Fold(IR.ANumber, WriteLimit, M);

1009 /* For instructions with A-indirection in the A-operand     */
1010 /* (A-number Indirect, A-number Predecrement,               */
1011 /* and A-number Postincrement A-modes):                     */

1012       if (IR.AMode == A_INDIRECT
1013           || IR.AMode == A_DECREMENT
1014           || IR.AMode == A_INCREMENT) {

1015 /* For instructions with Predecrement A-mode, the A-Field   */
1016 /* of the instruction in Core currently pointed to by the   */
1017 /* Pointer A is decremented (M - 1 is added).               */

1018          if (IR.AMode == A_DECREMENT) {
1019             Core[((PC + WPA) % M)].ANumber =
1020                (Core[((PC + WPA) % M)].ANumber + M - 1) % M;
1021          };

1022 /* For instructions with Postincrement A-mode, the A-Field  */
1023 /* of the instruction in Core currently pointed to by the   */
1024 /* Pointer A will be incremented.                           */

1025          if (IR.AMode == A_INCREMENT) {
1026             PIP = (PC + WPA) % M;
1027          };

1028 /* For instructions with A-indirection in the A-operand,    */
1029 /* Pointer A ultimately points to the instruction           */
1030 /* Core[((PC + PCA) % M)].ANumber away, relative to the     */
1031 /* instruction pointed to by Pointer A.                     */

1032          RPA = Fold(
1033             (RPA + Core[((PC + RPA) % M)].ANumber), ReadLimit, M
1034          );
1035          WPA = Fold(
1036             (WPA + Core[((PC + WPA) % M)].ANumber), WriteLimit, M
1037          );

1038       };

1039 /* For instructions with B-indirection in the A-operand     */
1040 /* (B-number Indirect, B-number Predecrement,               */
1041 /* and B-number Postincrement A-modes):                     */

1042       if (IR.AMode == B_INDIRECT
1043           || IR.AMode == B_DECREMENT
1044           || IR.AMode == B_INCREMENT) {

1045 /* For instructions with Predecrement A-mode, the B-Field   */
1046 /* of the instruction in Core currently pointed to by the   */
1047 /* Pointer A is decremented (M - 1 is added).               */

1048          if (IR.AMode == DECREMENT) {
1049             Core[((PC + WPA) % M)].BNumber =
1050                (Core[((PC + WPA) % M)].BNumber + M - 1) % M;
1051          };

1052 /* For instructions with Postincrement A-mode, the B-Field  */
1053 /* of the instruction in Core currently pointed to by the   */
1054 /* Pointer A will be incremented.                           */

1055          if (IR.AMode == INCREMENT) {
1056             PIP = (PC + WPA) % M;
1057          };

1058 /* For instructions with B-indirection in the A-operand,    */
1059 /* Pointer A ultimately points to the instruction           */
1060 /* Core[((PC + PCA) % M)].BNumber away, relative to the     */
1061 /* instruction pointed to by Pointer A.                     */

1062          RPA = Fold(
1063             (RPA + Core[((PC + RPA) % M)].BNumber), ReadLimit, M
1064          );
1065          WPA = Fold(
1066             (WPA + Core[((PC + WPA) % M)].BNumber), WriteLimit, M
1067          );

1068       };
1069    };

1070 /* The Instruction Register A is a copy of the instruction  */
1071 /* pointed to by Pointer A.                                 */

1072    IRA = Core[((PC + RPA) % M)];

1073 /* If the A-mode was post-increment, now is the time to     */
1074 /* increment the instruction in core.                       */

1075    if (IR.AMode == A_INCREMENT) {
1076            Core[PIP].ANumber = (Core[PIP].ANumber + 1) % M;
1077            }
1078    else if (IR.AMode == B_INCREMENT) {
1079            Core[PIP].BNumber = (Core[PIP].BNumber + 1) % M;
1080            };

1081 /* The Pointer B and the Instruction Register B are         */
1082 /* evaluated in the same manner as their A counterparts.    */

1083    if (IR.BMode == IMMEDIATE) {
1084       RPB = WPB = 0;
1085    } else {
1086       RPB = Fold(IR.BNumber, ReadLimit, M);
1087       WPB = Fold(IR.BNumber, WriteLimit, M);
1088       if (IR.BMode == A_INDIRECT
1089           || IR.BMode == A_DECREMENT
1090           || IR.BMode == A_INCREMENT) {
1091          if (IR.BMode == A_DECREMENT) {
1092             Core[((PC + WPB) % M)].ANumber =
1093                (Core[((PC + WPB) % M)].ANumber + M - 1) % M
1094             ;
1095          } else if (IR.BMode == A_INCREMENT) {
1096             PIP = (PC + WPB) % M;
1097          };
1098          RPB = Fold(
1099             (RPB + Core[((PC + RPB) % M)].ANumber), ReadLimit, M
1100          );
1101          WPB = Fold(
1102             (WPB + Core[((PC + WPB) % M)].ANumber), WriteLimit, M
1103          );
1104       };
1105       if (IR.BMode == B_INDIRECT
1106           || IR.BMode == B_DECREMENT
1107           || IR.BMode == B_INCREMENT) {
1108          if (IR.BMode == B_DECREMENT) {
1109             Core[((PC + WPB) % M)].BNumber =
1110                (Core[((PC + WPB) % M)].BNumber + M - 1) % M
1111             ;
1112          } else if (IR.BMode == B_INCREMENT) {
1113             PIP = (PC + WPB) % M;
1114          };
1115          RPB = Fold(
1116             (RPB + Core[((PC + RPB) % M)].BNumber), ReadLimit, M
1117          );
1118          WPB = Fold(
1119             (WPB + Core[((PC + WPB) % M)].BNumber), WriteLimit, M
1120          );
1121       };
1122    };
1123    IRB = Core[((PC + RPB) % M)];

1124    if (IR.BMode == A_INCREMENT) {
1125            Core[PIP].ANumber = (Core[PIP].ANumber + 1) % M;
1126            }
1127    else if (IR.BMode == INCREMENT) {
1128            Core[PIP].BNumber = (Core[PIP].BNumber + 1) % M;
1129            };

1130 /* Execution of the instruction can now proceed.            */

1131    switch (IR.Opcode) {

1132 /* Instructions with a DAT opcode have no further function. */
1133 /* The current task's Program Counter is not updated and is */
1134 /* not returned to the task queue, effectively removing the */
1135 /* task.                                                    */

1136    case DAT: noqueue:
1137       break;


1138 /* MOV replaces the B-target with the A-value and queues    */
1139 /* the next instruction.                                    */

1140    case MOV:
1141       switch (IR.Modifier) {

1142 /* Replaces A-number with A-number.                         */

1143       case A:
1144          Core[((PC + WPB) % M)].ANumber = IRA.ANumber;
1145          break;

1146 /* Replaces B-number with B-number.                         */

1147       case B:
1148          Core[((PC + WPB) % M)].BNumber = IRA.BNumber;
1149          break;

1150 /* Replaces B-number with A-number.                         */

1151       case AB:
1152          Core[((PC + WPB) % M)].BNumber = IRA.ANumber;
1153          break;

1154 /* Replaces A-number with B-number.                         */

1155       case BA:
1156          Core[((PC + WPB) % M)].ANumber = IRA.BNumber;
1157          break;

1158 /* Replaces A-number with A-number and B-number with        */
1159 /* B-number.                                                */

1160       case F:
1161          Core[((PC + WPB) % M)].ANumber = IRA.ANumber;
1162          Core[((PC + WPB) % M)].BNumber = IRA.BNumber;
1163          break;

1164 /* Replaces B-number with A-number and A-number with        */
1165 /* B-number.                                                */

1166       case X:
1167          Core[((PC + WPB) % M)].BNumber = IRA.ANumber;
1168          Core[((PC + WPB) % M)].ANumber = IRA.BNumber;
1169          break;

1170 /* Copies entire instruction.                               */

1171       case I:
1172          Core[((PC + WPB) % M)] = IRA;
1173          break;

1174       default:
1175          return(UNDEFINED);
1176          break;
1177       };

1178 /* Queue up next instruction.                               */
1179       Queue(W, ((PC + 1) % M));
1180       break;

1181 /* Arithmetic instructions replace the B-target with the    */
1182 /* "op" of the A-value and B-value, and queue the next      */
1183 /* instruction.  "op" can be the sum, the difference, or    */
1184 /* the product.                                             */

1185 #define ARITH(op) \
1186       switch (IR.Modifier) { \
1187       case A: \
1188          Core[((PC + WPB) % M)].ANumber = \
1189             (IRB.ANumber op IRA.ANumber) % M \
1190          ; \
1191          break; \
1192       case B: \
1193          Core[((PC + WPB) % M)].BNumber = \
1194             (IRB.BNumber op IRA.BNumber) % M \
1195          ; \
1196          break; \
1197       case AB: \
1198          Core[((PC + WPB) % M)].BNumber = \
1199             (IRB.ANumber op IRA.BNumber) % M \
1200          ; \
1201          break; \
1202       case BA: \
1203          Core[((PC + WPB) % M)].ANumber = \
1204             (IRB.BNumber op IRA.ANumber) % M \
1205          ; \
1206          break; \
1207       case F: \
1208       case I: \
1209          Core[((PC + WPB) % M)].ANumber = \
1210             (IRB.ANumber op IRA.ANumber) % M \
1211          ; \
1212          Core[((PC + WPB) % M)].BNumber = \
1213             (IRB.BNumber op IRA.BNumber) % M \
1214          ; \
1215          break; \
1216       case X: \
1217          Core[((PC + WPB) % M)].BNumber = \
1218             (IRB.ANumber op IRA.BNumber) % M \
1219          ; \
1220          Core[((PC + WPB) % M)].ANumber = \
1221             (IRB.BNumber op IRA.ANumber) % M \
1222          ; \
1223          break; \
1224       default: \
1225          return(UNDEFINED); \
1226          break; \
1227       }; \
1228       Queue(W, ((PC + 1) % M)); \
1229       break;

1230    case ADD: ARITH(+)
1231    case SUB: ARITH(+ M -)
1232    case MUL: ARITH(*)

1233 /* DIV and MOD replace the B-target with the integral       */
1234 /* quotient (for DIV) or remainder (for MOD) of the B-value */
1235 /* by the A-value, and queues the next instruction.         */
1236 /* Process is removed from task queue if A-value is zero.   */

1237 #define ARITH_DIV(op) \
1238       switch (IR.Modifier) { \
1239       case A: \
1240          if (IRA.ANumber != 0) \
1241             Core[((PC + WPB) % M)].ANumber = IRB.ANumber op IRA.ANumber; \
1242          break; \
1243       case B: \
1244          if (IRA.BNumber != 0) \
1245             Core[((PC + WPB) % M)].BNumber = IRB.BNumber op IRA.BNumber; \
1246          else goto noqueue; \
1247          break; \
1248       case AB: \
1249          if (IRA.ANumber != 0) \
1250             Core[((PC + WPB) % M)].BNumber = IRB.BNumber op IRA.ANumber; \
1251          else goto noqueue; \
1252          break; \
1253       case BA: \
1254          if (IRA.BNumber != 0) \
1255             Core[((PC + WPB) % M)].ANumber = IRB.ANumber op IRA.BNumber; \
1256          else goto noqueue; \
1257          break; \
1258       case F: \
1259       case I: \
1260          if (IRA.ANumber != 0) \
1261             Core[((PC + WPB) % M)].ANumber = IRB.ANumber op IRA.ANumber; \
1262          if (IRA.BNumber != 0) \
1263             Core[((PC + WPB) % M)].BNumber = IRB.BNumber op IRA.BNumber; \
1264          if ((IRA.ANumber == 0) || (IRA.BNumber == 0)) \
1265             goto noqueue; \
1266          break; \
1267       case X: \
1268          if (IRA.ANumber != 0) \
1269             Core[((PC + WPB) % M)].BNumber = IRB.BNumber op IRA.ANumber; \
1270          if (IRA.BNumber != 0) \
1271             Core[((PC + WPB) % M)].ANumber = IRB.ANumber op IRA.BNumber; \
1272          if ((IRA.ANumber == 0) || (IRA.BNumber == 0)) \
1273             goto noqueue; \
1274          break; \
1275       default: \
1276          return(UNDEFINED); \
1277          break; \
1278       }; \
1279       Queue(W, ((PC + 1) % M)); \
1280       break;

1281    case DIV: ARITH_DIV(/)
1282    case MOD: ARITH_DIV(%)

1283 /* JMP queues the sum of the Program Counter and the        */
1284 /* A-pointer.                                               */

1285    case JMP:
1286       Queue(W, RPA);
1287       break;


1288 /* JMZ queues the sum of the Program Counter and Pointer A  */
1289 /* if the B-value is zero.  Otherwise, it queues the next   */
1290 /* instruction.                                             */

1291    case JMZ:
1292       switch (IR.Modifier) {
1293       case A:
1294       case BA:
1295          if (IRB.ANumber == 0) {
1296             Queue(W, RPA);
1297          } else {
1298             Queue(W, ((PC + 1) % M));
1299          };
1300          break;
1301       case B:
1302       case AB:
1303          if (IRB.BNumber == 0) {
1304             Queue(W, RPA);
1305          } else {
1306             Queue(W, ((PC + 1) % M));
1307          };
1308          break;
1309       case F:
1310       case X:
1311       case I:
1312          if ( (IRB.ANumber == 0) && (IRB.BNumber == 0) ) {
1313             Queue(W, RPA);
1314          } else {
1315             Queue(W, ((PC + 1) % M));
1316          };
1317          break;
1318       default:
1319          return(UNDEFINED);
1320          break;
1321       };
1322       break;


1323 /* JMN queues the sum of the Program Counter and Pointer A  */
1324 /* if the B-value is not zero.  Otherwise, it queues the    */
1325 /* next instruction.                                        */

1326    case JMN:
1327       switch (IR.Modifier) {
1328       case A:
1329       case BA:
1330          if (IRB.ANumber != 0) {
1331             Queue(W, RPA);
1332          } else {
1333             Queue(W, ((PC + 1) % M));
1334          };
1335          break;
1336       case B:
1337       case AB:
1338          if (IRB.BNumber != 0) {
1339             Queue(W, RPA);
1340          } else {
1341             Queue(W, ((PC + 1) % M));
1342          };
1343          break;
1344       case F:
1345       case X:
1346       case I:
1347          if ( (IRB.ANumber != 0) || (IRB.BNumber != 0) ) {
1348             Queue(W, RPA);
1349          } else {
1350             Queue(W, ((PC + 1) % M));
1351          };
1352          break;
1353       default:
1354          return(UNDEFINED);
1355          break;
1356       };
1357       break;


1358 /* DJN (Decrement Jump if Not zero) decrements the B-value  */
1359 /* and the B-target, then tests if the B-value is zero.  If */
1360 /* the result is not zero, the sum of the Program Counter   */
1361 /* and Pointer A is queued.  Otherwise, the next            */
1362 /* instruction is queued.                                   */

1363    case DJN:
1364       switch (IR.Modifier) {
1365       case A:
1366       case BA:
1367          Core[((PC + WPB) % M)].ANumber =
1368             (Core[((PC + WPB) % M)].ANumber + M - 1) % M
1369          ;
1370          IRB.ANumber -= 1;
1371          if (IRB.ANumber != 0) {
1372             Queue(W, RPA);
1373          } else {
1374             Queue(W, ((PC + 1) % M));
1375          };
1376          break;
1377       case B:
1378       case AB:
1379          Core[((PC + WPB) % M)].BNumber =
1380             (Core[((PC + WPB) % M)].BNumber + M - 1) % M
1381          ;
1382          IRB.BNumber -= 1;
1383          if (IRB.BNumber != 0) {
1384             Queue(W, RPA);
1385          } else {
1386             Queue(W, ((PC + 1) % M));
1387          };
1388          break;
1389       case F:
1390       case X:
1391       case I:
1392          Core[((PC + WPB) % M)].ANumber =
1393             (Core[((PC + WPB) % M)].ANumber + M - 1) % M
1394          ;
1395          IRB.ANumber -= 1;
1396          Core[((PC + WPB) % M)].BNumber =
1397             (Core[((PC + WPB) % M)].BNumber + M - 1) % M
1398          ;
1399          IRB.BNumber -= 1;
1400          if ( (IRB.ANumber != 0) || (IRB.BNumber != 0) ) {
1401             Queue(W, RPA);
1402          } else {
1403             Queue(W, ((PC + 1) % M));
1404          };
1405          break;
1406       default:
1407          return(UNDEFINED);
1408          break;
1409       };
1410       break;


1411 /* SEQ/CMP compares the A-value and the B-value. If there   */
1412 /* are no differences, then the instruction after the next  */
1413 /* instruction is queued.  Otherwise, the next instrution   */
1414 /* is queued.                                               */

1415    case CMP:
1416       switch (IR.Modifier) {
1417       case A:
1418          if (IRA.ANumber == IRB.ANumber) {
1419             Queue(W, ((PC + 2) % M));
1420          } else {
1421             Queue(W, ((PC + 1) % M));
1422          };
1423          break;
1424       case B:
1425          if (IRA.BNumber == IRB.BNumber) {
1426             Queue(W, ((PC + 2) % M));
1427          } else {
1428             Queue(W, ((PC + 1) % M));
1429          };
1430          break;
1431       case AB:
1432          if (IRA.ANumber == IRB.BNumber) {
1433             Queue(W, ((PC + 2) % M));
1434          } else {
1435             Queue(W, ((PC + 1) % M));
1436          };
1437          break;
1438       case BA:
1439          if (IRA.BNumber == IRB.ANumber) {
1440             Queue(W, ((PC + 2) % M));
1441          } else {
1442             Queue(W, ((PC + 1) % M));
1443          };
1444          break;
1445       case F:
1446          if ( (IRA.ANumber == IRB.ANumber) &&
1447               (IRA.BNumber == IRB.BNumber)
1448          ) {
1449             Queue(W, ((PC + 2) % M));
1450          } else {
1451             Queue(W, ((PC + 1) % M));
1452          };
1453          break;
1454       case X:
1455          if ( (IRA.ANumber == IRB.BNumber) &&
1456               (IRA.BNumber == IRB.ANumber)
1457          ) {
1458             Queue(W, ((PC + 2) % M));
1459          } else {
1460             Queue(W, ((PC + 1) % M));
1461          };
1462          break;
1463       case I:
1464          if ( (IRA.Opcode == IRB.Opcode) &&
1465               (IRA.Modifier == IRB.Modifier) &&
1466               (IRA.AMode == IRB.AMode) &&
1467               (IRA.ANumber == IRB.ANumber) &&
1468               (IRA.BMode == IRB.BMode) &&
1469               (IRA.BNumber == IRB.BNumber)
1470          ) {
1471             Queue(W, ((PC + 2) % M));
1472          } else {
1473             Queue(W, ((PC + 1) % M));
1474          };
1475          break;
1476       default:
1477          return(UNDEFINED);
1478          break;
1479       };
1480       break;


1481 /* SNE compares the A-value and the B-value. If there       */
1482 /* is a difference, then the instruction after the next     */
1483 /* instruction is queued.  Otherwise, the next instrution   */
1484 /* is queued.                                               */

1485    case SNE:
1486       switch (IR.Modifier) {
1487       case A:
1488          if (IRA.ANumber != IRB.ANumber) {
1489             Queue(W, ((PC + 2) % M));
1490          } else {
1491             Queue(W, ((PC + 1) % M));
1492          };
1493          break;
1494       case B:
1495          if (IRA.BNumber != IRB.BNumber) {
1496             Queue(W, ((PC + 2) % M));
1497          } else {
1498             Queue(W, ((PC + 1) % M));
1499          };
1500          break;
1501       case AB:
1502          if (IRA.ANumber != IRB.BNumber) {
1503             Queue(W, ((PC + 2) % M));
1504          } else {
1505             Queue(W, ((PC + 1) % M));
1506          };
1507          break;
1508       case BA:
1509          if (IRA.BNumber != IRB.ANumber) {
1510             Queue(W, ((PC + 2) % M));
1511          } else {
1512             Queue(W, ((PC + 1) % M));
1513          };
1514          break;
1515       case F:
1516          if ( (IRA.ANumber != IRB.ANumber) ||
1517               (IRA.BNumber != IRB.BNumber)
1518          ) {
1519             Queue(W, ((PC + 2) % M));
1520          } else {
1521             Queue(W, ((PC + 1) % M));
1522          };
1523          break;
1524       case X:
1525          if ( (IRA.ANumber != IRB.BNumber) ||
1526               (IRA.BNumber != IRB.ANumber)
1527          ) {
1528             Queue(W, ((PC + 2) % M));
1529          } else {
1530             Queue(W, ((PC + 1) % M));
1531          };
1532          break;
1533       case I:
1534          if ( (IRA.Opcode != IRB.Opcode) ||
1535               (IRA.Modifier != IRB.Modifier) ||
1536               (IRA.AMode != IRB.AMode) ||
1537               (IRA.ANumber != IRB.ANumber) ||
1538               (IRA.BMode != IRB.BMode) ||
1539               (IRA.BNumber != IRB.BNumber)
1540          ) {
1541             Queue(W, ((PC + 2) % M));
1542          } else {
1543             Queue(W, ((PC + 1) % M));
1544          };
1545          break;
1546       default:
1547          return(UNDEFINED);
1548          break;
1549       };
1550       break;


1551 /* SLT (Skip if Less Than) queues the instruction after the */
1552 /* next instruction if A-value is less than B-value.        */
1553 /* Otherwise, the next instruction is queued.  Note that no */
1554 /* value is less than zero because only positive values can */
1555 /* be represented in core.                                  */

1556    case SLT :
1557       switch (IR.Modifier) {
1558       case A:
1559          if (IRA.ANumber < IRB.ANumber) {
1560             Queue(W, ((PC + 2) % M));
1561          } else {
1562             Queue(W, ((PC + 1) % M));
1563          };
1564          break;
1565       case B:
1566          if (IRA.BNumber < IRB.BNumber) {
1567             Queue(W, ((PC + 2) % M));
1568          } else {
1569             Queue(W, ((PC + 1) % M));
1570          };
1571          break;
1572       case AB:
1573          if (IRA.ANumber < IRB.BNumber) {
1574             Queue(W, ((PC + 2) % M));
1575          } else {
1576             Queue(W, ((PC + 1) % M));
1577          };
1578          break;
1579       case BA:
1580          if (IRA.BNumber < IRB.ANumber) {
1581             Queue(W, ((PC + 2) % M));
1582          } else {
1583             Queue(W, ((PC + 1) % M));
1584          };
1585          break;
1586       case F:
1587       case I:
1588          if ( (IRA.ANumber < IRB.ANumber) &&
1589               (IRA.BNumber < IRB.BNumber)
1590          ) {
1591             Queue(W, ((PC + 2) % M));
1592          } else {
1593             Queue(W, ((PC + 1) % M));
1594          };
1595          break;
1596       case X:
1597          if ( (IRA.ANumber < IRB.BNumber) &&
1598               (IRA.BNumber < IRB.ANumber)
1599          ) {
1600             Queue(W, ((PC + 2) % M));
1601          } else {
1602             Queue(W, ((PC + 1) % M));
1603          };
1604          break;
1605       default:
1606          return(UNDEFINED);
1607          break;
1608       };
1609       break;


1610 /* SPL queues the next instruction and also queues the sum  */
1611 /* of the Program Counter and Pointer A.                    */

1612    case SPL:
1613       Queue(W, ((PC + 1) % M));
1614       Queue(W, RPA);
1615       break;


1616 /* NOP queues the next instruction.                         */

1617    case NOP:
1618       Queue(W, ((PC + 1) % M));
1619       break;


1620 /* Any other opcode is undefined.                           */

1621    default:
1622       return(UNDEFINED);
1623    };


1624 /* We are finished.                                         */

1625    return(SUCCESS);
1626 }

1627 6. Validation Suite

1628 6.1 Purpose and Requirements
1629 This validation suite exists to help developers test the compatibility
1630 of their Core War systems with the requirements set up in this
1631 standard.

1632 6.2 Assembly To Load File Test

1633 6.3 MARS tests

1634 6.3.1   DAT Tests
1635 6.3.2   MOV Tests
1636 6.3.3   ADD Tests
1637 6.3.4   SUB Tests
1638 6.3.5   MUL Tests
1639 6.3.6   DIV Tests
1640 6.3.7   MOD Tests
1641 6.3.8   JMP Tests
1642 6.3.9   JMZ Tests
1643 6.3.10  JMN Tests
1644 6.3.11  DJN Tests
1645 6.3.12  SEQ/CMP Tests
1646 6.3.13  SNE Tests
1647 6.3.14  SLT Tests
1648 6.3.15  SPL Tests
1649 6.3.16  NOP Tests


1650 7. Glossary and Index
1651 alphanumeric    Any of the characters A-Za-z0-9 and the underscore.

1652 assembly file   A file containing Redcode instructions.

1653 battle          A contest between two or more warriors.

1654 core size       See section 4.2

1655 Core War        A game in which programs compete for control of a
1656                 computer called a Memory Array Redcode Simulator.

1657 Core Wars       More than one game of Core War.

1658 cycle           See section 4.2

1659 Dwarf           See sections 2.7 and 3.6

1660 initial instruction
1661                 See section 4.2

1662 instruction     A line of Redcode or object code indicating an action
1663                 for MARS to execute.

1664 instruction limit
1665                 See section 4.2

1666 loader          A program or that part of a program which loads
1667                 warriors into a MARS.

1668 load file       A file containing a warrior's instructions in an
1669                 assembled format.  Any MARS program can be used with
1670                 any and all Redcode assemblers which produce load
1671                 files, allowing customized Core War systems.

1672 MARS            An acronym for Memory Array Redcode Simulator.  The
1673                 computer in which Core War warriors run.

1674 newline         A linefeed, carriage-return, or combination of linefeed
1675                 and carriage-return.  Whichever newline is native to
1676                 the host operating system.

1677 object code     The internal representation of a MARS instruction.

1678 read distance   See section 4.2

1679 Redcode         The assembly language of Core War.

1680 tournament      A series of battles in which points, based upon the
1681                 degree of success, are awarded for each battle and
1682                 accumulated by each warrior (or programmer, depending
1683                 upon the type of tournament).

1684 warrior         A Redcode program.

1685 whitespace      The space and tab characters.

1686 write distance  See section 4.2


1687 A. Differences Between Standards

1688 A.1 Purpose
1689 This appendix lists some of the major differences between this standard
1690 and those standards which preceded it.  The purpose is to help those
1691 who are familiar with a previous standard or standards to quickly
1692 understand those items which are new or have changed.


1693 A.2 Changes

1694 A.2.1 Assembly Files
1695 A comma is required for operand separation.

1696 Parenthetical expressions are allowed.

1697 There is a new pseudo-opcode, ORG, for specifying the first logical
1698 instruction.

1699 There is a new operator, modulus '%', for determining the remainder
1700 of integer division.

1701 A.2.1.1 ICWS'86 to ICWS'94 Conversion
1702 If a modifier is missing, it is assembled according to conversion
1703 rules that depend on whether the ICWS'86 or '88 standard is emulated.
1704 By default, a MARS should use the ICWS'88 conversion rules. Emulation
1705 of ICWS'86 is optional.

1706     Opcode                  A-mode     B-mode     modifier
1707     ---------------------------------------------------------
1708     DAT                        #$@<>*{}   #$@<>*{}   F
1709     MOV,CMP,SEQ,SNE            #          #$@<>*{}   AB
1710                                $@<>*{}    #          B
1711                                $@<>*{}    $@<>*{}    I
1712     ADD,SUB,MUL,DIV,MOD        #          #$@<>*{}   AB
1713                                $@<>*{}    #$@<>*{}   B
1714     SLT                        #          #$@<>*{}   AB
1715                                $@<>*{}    #$@<>*{}   B
1716     JMP,JMZ,JMN,DJN,SPL,NOP    #$@<>*{}   #$@<>*{}   B
1717     ---------------------------------------------------------

1718 A.2.1.2 ICWS'88 to ICWS'94 Conversion
1719 The default modifier for ICWS'88 emulation is determined according
1720 to the table below.

1721     Opcode                     A-mode     B-mode     modifier
1722     ---------------------------------------------------------
1723     DAT                        #$@<>*{}   #$@<>*{}   F
1724     MOV,CMP,SEQ,SNE            #          #$@<>*{}   AB
1725                                $@<>*{}    #          B
1726                                $@<>*{}    $@<>*{}    I
1727     ADD,SUB,MUL,DIV,MOD        #          #$@<>*{}   AB
1728                                $@<>*{}    #          B
1729                                $@<>*{}    $@<>*{}    F
1730     SLT                        #          #$@<>*{}   AB
1731                                $@<>*{}    #$@<>*{}   B
1732     JMP,JMZ,JMN,DJN,SPL,NOP    #$@<>*{}   #$@<>*{}   B
1733     ---------------------------------------------------------

1734 A.2.2 Load Files
1735 A load file format is specified for the first time.  (An object code
1736 did exist for ICWS'86).


1737 A.2.3 MARS
1738 There are no illegal instructions.

1739 The following addressing modes have been added:
1740 A-number indirect, A-number predecrement, A-number postincrement,
1741 and B-number postincrement.

1742 MUL, DIV, MOD, SNE, and NOP have been added.
1743 SEQ is an alias for CMP.

1744 Opcode modifiers have been added.

1745 Read and Write distance limitations have been imposed.

```

## File: corewar\tests\mars_test.py

- Extension: .py
- Language: python
- Size: 4392 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
#! /usr/bin/env python
#! coding: utf-8

import os
import re
import unittest

from corewar import redcode, mars

DEFAULT_ENV = {'CORESIZE': 8000, 'MAXLENGTH': 100}

class TestMars(unittest.TestCase):

    def test_dwarf_versus_sitting_duck(self):

        dwarf_code = """
            ;name dwarf
            ;author A. K. Dewdney

            org start

            loop    add.ab  #2004, start
            start   mov     2,     2
                    jmp     loop
        """
        sitting_duck_code = """
            nop
            nop
            nop
            nop
            nop
        """

        dwarf        = redcode.parse(dwarf_code.split('\n'), DEFAULT_ENV)
        sitting_duck = redcode.parse(sitting_duck_code.split('\n'), DEFAULT_ENV)

        simulation = mars.MARS(warriors=[dwarf, sitting_duck])

        # run simulation for at most
        for x in xrange(8000):
            simulation.step()
            if not dwarf.task_queue or not sitting_duck.task_queue:
                break
        else:
            self.fail("Running for too long and both warriors still alive")

        self.assertEquals(1, len(dwarf.task_queue))
        self.assertEquals(0, len(sitting_duck.task_queue))

    def test_validate(self):

        current_path = os.path.dirname(os.path.realpath(__file__))

        with open(os.path.join(current_path, "..", "warriors", "validate.red")) as f:
            validate = redcode.parse(f, DEFAULT_ENV)

        simulation = mars.MARS(warriors=[validate], randomize=False)

        for i in xrange(8000):
            simulation.step()
            if not validate.task_queue:
                self.fail("Interpreter is not ICWS88-compliant. died in %d steps" % i)

    def test_crazy_warrrior(self):
        self.warrior_step_by_step("crazy.red", "crazy-steps.red", -22, 22)

    def test_validate_warrior(self):
        self.warrior_step_by_step("validate.red", "validate-steps.red", 0, 90)

    def warrior_step_by_step(self, warrior_filename, log_filename, core_start, core_end):

        current_path = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_path, "..", "warriors", warrior_filename)) as f:
            test_w = redcode.parse(f, DEFAULT_ENV)

        simulation = mars.MARS(warriors=[test_w], randomize=False)

        nth = 0

        with open(os.path.join(current_path, log_filename)) as f:
            accum_lines = []
            for n, line in enumerate(f):
                m = re.match(r';ACTIVE: ([0-9]{5})', line)
                if line.startswith(';ACTIVE:') and not m:
                    self.fail("Fatal error in regular expression line %d" % n)

                if m:
                    next_queued = int(m.group(1))
                    # has a full program, parse it
                    expected = redcode.parse(accum_lines)

                    # compare with next in queue
                    if not test_w.task_queue:
                        self.fail("No tasks in queue. step %d, line %d" % (nth, n))
                    if test_w.task_queue[0] != next_queued:
                        self.fail("Task address does not match (%d != %d). step %d, line %d" %
                                  (next_queued, test_w.task_queue[0], nth, n))

                    # compare it with the current state
                    for e, i in zip(expected, simulation.core[core_start:core_end]):
                        if e != i:
                            print
                            x = core_start
                            for e, i in zip(expected, simulation.core[core_start:core_end]):
                                if e != i:
                                    print "%05d %s != %s" % (x, str(e), str(i))
                                else:
                                    print "%05d %s == %s" % (x, str(e), str(i))
                                x += 1
                            self.fail("Core don't match, step %d, line %d" % (nth, n))

                    # next state
                    simulation.step()

                    # throw away and start over
                    accum_lines = []
                    nth += 1
                else:
                    accum_lines.append(line)


if __name__ == '__main__':
    unittest.main()


```

## File: corewar\tests\redcode_test.py

- Extension: .py
- Language: python
- Size: 1263 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python
#! /usr/bin/env python
#! coding: utf-8

import unittest

from corewar.redcode import *

DEFAULT_ENV = {'CORESIZE': 8000}

class TestRedcodeAssembler(unittest.TestCase):

    def test_1(self):

        input = """
                ;name dwarf
                ;author A. K. Dewdney
                ;assert CORESIZE % 4 == 0

                org start
                step equ 2004

                loop    add.ab  #step,  start
                start   mov     2, 2
                        jmp.f   $loop ;go back and start over
                """
        warrior = parse(input.split('\n'), DEFAULT_ENV)

        self.assertEquals(1, warrior.start)
        self.assertEquals('dwarf', warrior.name)
        self.assertEquals('A. K. Dewdney', warrior.author)
        self.assertEquals(3, len(warrior))

        self.assertEquals(Instruction(ADD, M_AB, IMMEDIATE, 2004, DIRECT, 1),
                          warrior.instructions[0])
        self.assertEquals(Instruction(MOV, M_I, DIRECT, 2, DIRECT, 2),
                          warrior.instructions[1])
        self.assertEquals(Instruction(JMP, M_F, DIRECT, -2, DIRECT, 0),
                          warrior.instructions[2])

if __name__ == '__main__':
    unittest.main()


```

## File: corewar\tests\__init__.py

- Extension: .py
- Language: python
- Size: 0 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```python

```

## File: prompts\crossover_prompt_0.txt

- Extension: .txt
- Language: plaintext
- Size: 335 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```plaintext
Crossover (combine) and mutate (change) the following Core War programs in a way that is likely to improve its performance (survive and kill other programs). Write only the new updated program (with comments explaining what it does) and nothing else. ONLY DEFINE LABELS ON THE SAME LINE AS AN INSTRUCTION. Wrap program around ``` tags.
```

## File: prompts\mutate_prompt_0.txt

- Extension: .txt
- Language: plaintext
- Size: 310 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```plaintext
Mutate (change) the following Core War program in a way that is likely to improve its performance (survive and kill other programs). Write only the new updated program (with comments explaining what it does) and nothing else. ONLY DEFINE LABELS ON THE SAME LINE AS AN INSTRUCTION. Wrap program around ``` tags.
```

## File: prompts\new_prompt_0.txt

- Extension: .txt
- Language: plaintext
- Size: 230 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```plaintext
Create a new valid Core War program in redcode. Be creative. Write only the new program (with comments explaining what it does) and nothing else. ONLY DEFINE LABELS ON THE SAME LINE AS AN INSTRUCTION. Wrap program around ``` tags.
```

## File: prompts\system_prompt_0.txt

- Extension: .txt
- Language: plaintext
- Size: 15341 bytes
- Created: 2026-01-14 15:04:50
- Modified: 2026-01-14 15:04:50

### Code

```plaintext
You are a useful coding assistant for Core War.

----BACKGROUND----
Core War is a game in which programs compete for control of a computer called MARS (for Memory Array Redcode Simulator).  Redcode is the name of the assembly language in which Core War programs, called warriors, are written.

----INSTRUCTION SET OPCODES----
DAT | MOV | ADD | SUB | MUL | DIV | MOD | JMP | JMZ | JMN | DJN | CMP | SEQ | SNE | SLT | SPL | NOP | ORG | EQU | END

DAT
No additional processing takes place.  This effectively removes the current task from the current warrior's task queue.

MOV
Move replaces the B-target with the A-value and queues the next instruction (PC + 1).

ADD
ADD replaces the B-target with the sum of the A-value and the B-value (A-value + B-value) and queues the next instruction (PC + 1).  ADD.I functions as ADD.F would.

SUB
SUB replaces the B-target with the difference of the B-value and the A-value (B-value - A-value) and queues the next instruction (PC + 1).  SUB.I functions as SUB.F would.

MUL
MUL replaces the B-target with the product of the A-value and the B-value (A-value * B-value) and queues the next instruction (PC + 1).  MUL.I functions as MUL.F would.

DIV
DIV replaces the B-target with the integral result of dividing the B-value by the A-value (B-value / A-value) and queues the next instruction (PC + 1).  DIV.I functions as DIV.F would. If the A-value is zero, the B-value is unchanged and the current task is removed from the warrior's task queue.  DIV.I, DIV.F, and DIV.X operate on pairs of operands.  If either component of the A-value is zero, the corresponding component of the B-value is unchanged (the other component is divided normally), and the current task is removed from the warrior queue.

MOD
MOD replaces the B-target with the integral remainder of dividing the B-value by the A-value (B-value % A-value) and queues the next instruction (PC + 1).  MOD.I functions as MOD.F would. If the A-value is zero, the B-value is unchanged and the current task is removed from the warrior's task queue.  MOD.I, MOD.F, and MOD.X operate on pairs of operands.  If either component of the A-value is zero, the corresponding component of the B-value is unchanged (the other component is divided normally), and the current task is removed from the warrior queue.

JMP
JMP queues the sum of the program counter and the A-pointer.

JMZ
JMZ tests the B-value to determine if it is zero.  If the B-value is zero, the sum of the program counter and the A-pointer is queued.  Otherwise, the next instruction is queued (PC + 1).  JMZ.I functions as JMZ.F would, i.e. it jumps if both the A-number and the B-number of the B-instruction are zero.

JMN
JMN tests the B-value to determine if it is zero.  If the B-value is not zero, the sum of the program counter and the A-pointer is queued.  Otherwise, the next instruction is queued (PC + 1).  JMN.I functions as JMN.F would, i.e. it jumps if the A-number or the B-number of the B-instruction (or both) is non-zero. This is the negation of the condition for JMZ.F.

DJN
DJN decrements the B-value and the B-target, then tests the B-value to determine if it is zero.  If the decremented B-value is not zero, the sum of the program counter and the A-pointer is queued.  Otherwise, the next instruction is queued (PC + 1).  DJN.I functions as DJN.F would, i.e. it decrements both both A/B-numbers of the B-value and the B-target, and jumps if one (or both) of the A/B-numbers of the B-value is non-zero.

SEQ and CMP
SEQ and CMP are synonymous opcodes.  SEQ is provided as an easy-to-remember mnemonic, and CMP is provided for backward compatibility.  They are completely equivalent.  SEQ (or CMP) compares the A-value to the B-value.  If the result of the comparison is equal, the instruction after the next instruction (PC + 2) is queued (skipping the next instruction).  Otherwise, the next instruction is queued (PC + 1).

SNE
SNE compares the A-value to the B-value.  If the result of the comparison is not equal, the instruction after the next instruction (PC + 2) is queued (skipping the next instruction).  Otherwise, the next instruction is queued (PC + 1).

SLT
SLT compares the A-value to the B-value.  If the A-value is less than the B-value, the instruction after the next instruction (PC + 2) is queued (skipping the next instruction).  Otherwise, the next instruction is queued (PC + 1).  SLT.I functions as SLT.F would, i.e.  the next instruction is skipped only if each of the A/B-numbers of the A-value is less than its B-value counterpart.

SPL
SPL queues the next instruction (PC + 1) and then queues the sum of the program counter and the A-pointer. If the queue is full, only the next instruction is queued.

NOP
NOP queues the next instruction (PC + 1).

ORG
ORG designates where the execution should begin (specify a label or location)

EQU
EQU defines a label as a number and replaces all instances of that label with that number.

END
END marks the end of the program.

----MODIFIERS----
A | B | AB | BA | F | X | I

Modifiers are appended to the opcodes with a dot. Example: "MOV.A". The modifiers are:

.A      Instructions use and write A-numbers.
.B      Instructions use and write B-numbers.
.AB     Instructions use the A-numbers of the A-instructions and the B-numbers of the B-instructions and write B-numbers.
.BA     Instructions use the B-numbers of the A-instructions and the A-numbers of the B-instructions and write A-numbers.
.F      Instructions use both the A-numbers and the B-numbers, using and writing A-to-A, B-to-B.
.X      Instructions use both the A-numbers and the B-numbers, using and writing A-to-B, B-to-A.
.I      Instructions use and write entire instructions.


----ADDRESS MODES----
# | $ | * | @ | { | < | } | > | e

Immediate '#'
An immediate mode operand merely serves as storage for data.  An immediate A/B-mode in the current instruction sets the A/B-pointer to zero.

Direct '$'
A direct mode operand indicates the offset from the program counter.  A direct A/B-mode in the current instruction means the A/B-pointer is a copy of the offset, the A/B-number of the current instruction.

A-number Indirect '*'
An A-number indirect mode operand indicates the primary offset (relative to the program counter) to the secondary offset (relative to the location of the instruction in which the secondary offset is contained).  An A-number indirect A/B-mode indicates that the A/B-pointer is the sum of the A/B-number of the current instruction (the primary offset) and the A-number of the instruction pointed to by the A/B-number of the current instruction (the secondary offset).

B-number Indirect '@'
A B-number indirect mode operand indicates the primary offset (relative to the program counter) to the secondary offset (relative to the location of the instruction in which the secondary offset is contained).  A B-number indirect A/B-mode indicates that the A/B-pointer is the sum of the A/B-number of the current instruction (the primary offset) and the B-number of the instruction pointed to by the A/B-number of the current instruction (the secondary offset).

A-number Predecrement Indirect '{'
An A-number predecrement indirect mode operand indicates the primary offset (relative to the program counter) to the secondary offset (relative to the location of the instruction in which the secondary offset is contained) which is decremented prior to use.  An A-number predecrement indirect A/B-mode indicates that the A/B-pointer is the sum of the A/B-number of the current instruction (the primary offset) and the decremented A-number of the instruction pointed to by the A/B-number of the current instruction (the secondary offset).

B-number Predecrement Indirect '<'
A B-number predecrement indirect mode operand indicates the primary offset (relative to the program counter) to the secondary offset (relative to the location of the instruction in which the secondary offset is contained) which is decremented prior to use.  A B-number predecrement indirect A/B-mode indicates that the A/B-pointer is the sum of the A/B-number of the current instruction (the primary offset) and the decremented B-number of the instruction pointed to by the A/B-number of the current instruction (the secondary offset).

A-number Postincrement Indirect '}'
An A-number postincrement indirect mode operand indicates the primary offset (relative to the program counter) to the secondary offset (relative to the location of the instruction in which the secondary offset is contained) which is incremented after the results of the operand evaluation are stored.  An A-number postincrement indirect A/B-mode indicates that the A/B-pointer is the sum of the A/B-number of the current instruction (the primary offset) and the A-number of the instruction pointed to by the A/B-number of the current instruction (the secondary offset).  The A-number of the instruction pointed to by the A/B-number of the current instruction is incremented after the A/B-instruction is stored, but before the B-operand is evaluated (for A-number postincrement indirect A-mode), or the operation is executed (for A-number postincrement indirect B-mode).

B-number Postincrement Indirect '>'
A B-number postincrement indirect mode operand indicates the primary offset (relative to the program counter) to the secondary offset (relative to the location of the instruction in which the secondary offset is contained) which is incremented after the results of the operand evaluation are stored.  A B-number postincrement indirect A/B-mode indicates that the A/B-pointer is the sum of the A/B-number of the current instruction (the primary offset) and the B-number of the instruction pointed to by the A/B-number of the current instruction (the secondary offset).  The B-number of the instruction pointed to by the A/B-number of the current instruction is incremented after the A/B-instruction is stored, but before the B-operand is evaluated (for B-number postincrement indirect A-mode), or the operation is executed (for B-number postincrement indirect B-mode).

----OTHER INFORMATION----
The field separator (comma) ',', the comment indicator (semicolon) ';', the arithmetic operators for addition '+', subtraction '-', multiplication '*', division '/', and  modulus '%', and opening '(' and closing ')' parentheses for precedence grouping.


----EXAMPLE REDCODE PROGRAM 1----
;name IMP
;author A. K. Dewdney

MOV.I   0, 1    ; move the current instruction to the next line

----EXAMPLE REDCODE PROGRAM 2----
;name IMP
;author A. K. Dewdney

mov.i   #1,     *0    ; move the current instruction (since the A pointer is set to 0 due to immediate addressing) to the location address stored at address 0's A pointer, which is 1, which is the next line.

----EXAMPLE REDCODE PROGRAM 3----
;redcode
;name          Dwarf
;author        A. K. Dewdney
;version       94.1
;date          April 29, 1993

;strategy      Bombs every fourth instruction.
;assert        CORESIZE % 4 == 0

        ORG     start              ; Indicates the instruction with
                                   ; the label "start" should be the
                                   ; first to execute.

step    EQU      4                 ; Replaces all occurrences of "step"
                                   ; with the character "4".

target  DAT.F   #0,     #0         ; Pointer to target instruction.
start   ADD.AB  #step,   target    ; Increments pointer by step.
        MOV.AB  #0,     @target    ; Bombs target instruction.
        JMP.A    start             ; Same as JMP.A -2.  Loops back to
                                   ; the instruction labelled "start".
        END

----EXAMPLE REDCODE PROGRAM 4----
;redcode
;name Validate 1.1R
;author Stefan Strack
;strategy System validation program - based on Mark Durham's validation suite
;
;   This program tests your corewar system for compliance with the ICWS88-
;   standard and compatibility with KotH. It self-ties (i.e. loops forever)
;   if the running system is ICWS88-compliant and uses in-register evaluation;
;   suicides (terminates) if the interpreter is not ICWS compliant and/or uses
;   in-memory evaluation. A counter at label 'flag' can be used to determine
;   where the exception occurred.
;
;   Tests:
;   -all opcodes and addressing modes
;   -ICWS88-style ADD/SUB
;   -ICWS88-style SPL
;   -correct timing
;   -in-memory vs. in-register evaluation
;   -core initialization
;
;   Version 1.1: added autodestruct in case process gets stuck


;assert MAXLENGTH >= 90

start   spl l1,count+1
        jmz <start,0
count   djn count,#36      ;time cycles
        sub #1,@start
clear   mov t1,<last+2     ;autodestruct if stuck
        jmp clear
t1      dat #0,#1
t2      dat #0,#3
l1      spl l2
        dat <t2,<t2
l2      cmp t1,t2
        jmp fail
        spl l4
        jmz l3,<0
t3      dat #0,#1
t4      dat #0,#2
l3      jmp @0,<0
l4      jmp <t5,#0
        jmp l5
t5      dat #0,#0
t6      dat #0,#-1
l5      cmp t3,t4
        jmp fail
        cmp t5,t6
        jmp fail
        jmp <t7,<t7
        jmp l6
t7      dat #0,#0
t8      dat #0,#-2
l6      cmp t7,t8
        jmp fail
        mov t9,<t9         ;test in-memory evaluation
t9      jmn l7,1
t10     jmn l7+1,1
l7      cmp t9,t10
        jmp fail
        mov @0,<t11
t11     jmn l8,1
t12     jmn l8+1,1
l8      cmp t11,t12
        jmp fail
        spl l9
        mov <t13,t14
t13     dat <0,#1
t14     dat <0,#1
t15     dat <0,#-1
l9      mov <t16,t16
t16     jmz l10,1
        jmp fail
l10     cmp t13,t15
        jmp fail
        add t17,<t17
t17     jmp 1,1
t18     jmp 2,1
        cmp t17,t18
        jmp fail
        add @0,<t19
t19     jmp 1,1
        jmp fail
        cmp t18,t19
        jmp fail
        spl l11            ;ICWS86 SPL will fail here
        cmp t20,t21
        jmp l12
        jmp fail
l11     sub <t20,t20
t20     dat #2,#1
t21     dat #0,#0
l12     cmp t20,t21
        jmp fail
t22     sub <t23,<t23
t23     jmp l13,1
t24     sub <-2,<1
t25     jmp l13+2,-1
l13     cmp t22,t24
        jmp fail
        cmp t23,t25
        jmp fail
        cmp start-1,t26    ;Core initialization dat 0,0
        jmp l14
        jmp fail
t26     dat #0,#0
l14     slt #0,count       ;check cycle timer
        jmp success
fail    mov count,flag     ;save counter for post-mortem debugging
        mov t1,count       ;kill counter
        jmp clear          ;and auto-destruct
flag    dat #0, #0
success mov flag,clear     ;cancel autodestruct
last    jmp 0              ;and loop forever

        end start

----IMPORTANT CONSTRAINTS----
The user will ask you to create and edit Core War programs. Remember the following very IMPORTANT ESSENTIAL rules.
Note that all memory addressing is relative to the current line number (or using labels handles this).
Start all programs with "ORG start" and end all programs with "END".
All labels should be lowercase.
All labels should be defined somewhere exactly once (especially the 'start' label).
All labels should only be defined on the same line as an instruction (i.e. lines with only a label are INVALID).

```


