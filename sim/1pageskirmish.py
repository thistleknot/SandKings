import random
import math
from enum import Enum
import os
import time
from PIL import Image, ImageDraw, ImageFont
import io

# ANSI color codes
class Colors:
    RED = '\033[91m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

class Action(Enum):
    HOLD = 0
    ADVANCE = 1
    RUSH = 2
    CHARGE = 3

class WoundEffect(Enum):
    NONE = 0
    SHAKEN = 1
    KNOCKED_OUT = 2

class TerrainType(Enum):
    NORMAL = 0
    COVER = 1
    DIFFICULT = 2
    DANGEROUS = 3

class WeaponType(Enum):
    MELEE = 0
    RANGED = 1
    INDIRECT = 2

class UnitType(Enum):
    HERO = 0
    TROOP = 1
    ELITE = 2

class Unit:
    def __init__(self, name, quality, defense, points, move_types, weapons, special_rules=None, tough=1, player_id=0, models=1):
        self.name = name
        self.quality = quality
        self.defense = defense
        self.points = points
        self.move_types = move_types
        self.weapons = weapons
        self.special_rules = special_rules if special_rules else {}
        self.tough = tough
        self.player_id = player_id
        
        # Model positions for unit cohesion
        self.models = models
        self.model_positions = []
        self.position = None
        self.elevation = 0
        self.wound_markers = 0
        self.shaken = False
        self.fatigued = False
        self.activated = False
        
        # Phase 3: Command Groups
        self.has_sergeant = False
        self.has_musician = False
        self.has_banner = False
        
        # Phase 3: Magic
        self.spell_tokens = 0
        self.max_spell_tokens = 6
        if "Caster" in self.special_rules:
            self.spell_tokens = self.special_rules["Caster"]
        
        # Phase 3: Deployment
        self.deployed_via_ambush = False
        
        # Visual effects for actions
        self.action_effect = None  # Will store temporary action display
        self.effect_duration = 0   # How long to show effect
        self.status_effects = set()  # Persistent status effects
        
    def set_position(self, position, elevation=0):
        """Set unit position and arrange models in cohesion"""
        self.position = position
        self.elevation = elevation
        self.model_positions = [position]
        
        # Place additional models within 1" cohesion
        if self.models > 1:
            for i in range(1, self.models):
                for attempt in range(10):
                    angle = random.uniform(0, 2 * math.pi)
                    distance = random.uniform(0.5, 1.0)
                    base_pos = random.choice(self.model_positions)
                    
                    new_x = base_pos[0] + distance * math.cos(angle)
                    new_y = base_pos[1] + distance * math.sin(angle)
                    new_pos = (round(new_x), round(new_y))
                    
                    if self.is_valid_model_position(new_pos):
                        self.model_positions.append(new_pos)
                        break
                else:
                    self.model_positions.append(position)
    
    def apply_action_effect(self, effect_type, duration=2, attacker_player=None):
        """Apply temporary visual effect with attacker's color"""
        self.action_effect = effect_type
        self.effect_duration = duration
        self.attacker_player = attacker_player  # Track who's attacking
    
    def add_status_effect(self, effect):
        """Add persistent status effect"""
        self.status_effects.add(effect)
    
    def remove_status_effect(self, effect):
        """Remove persistent status effect"""
        self.status_effects.discard(effect)
    
    def get_display_symbol(self):
        """Get the symbol to display for this unit"""
        # Priority: Action effects > Status effects > Unit type
        if self.action_effect and self.effect_duration > 0:
            return self.action_effect
        
        # Check for status effects
        if 'UNCONSCIOUS' in self.status_effects:
            return 'U'
        if 'POISONED' in self.status_effects:
            return 'P'
        if 'SHAKEN' in self.status_effects:
            return 'K'  # sHaKen
        if 'BURNING' in self.status_effects:
            return 'B'
        if 'FROZEN' in self.status_effects:
            return 'F'
        
        # Default unit symbols
        if "Hero" in self.special_rules:
            return 'H'
        elif self.has_sergeant:
            return 'S'
        elif self.has_musician:
            return 'M'
        elif self.has_banner:
            return 'N'
        elif self.player_id == 0:
            return '1'
        else:
            return '2'
    
    def get_display_color(self):
        """Get the color to display for this unit"""
        # Action effects show in ATTACKER's color, not target's color
        if self.action_effect and self.effect_duration > 0:
            if hasattr(self, 'attacker_player') and self.attacker_player is not None:
                return Colors.RED if self.attacker_player == 0 else Colors.BLUE
            else:
                # Fallback to target's color if no attacker info
                return Colors.RED if self.player_id == 0 else Colors.BLUE
        
        # Normal unit colors
        return Colors.RED if self.player_id == 0 else Colors.BLUE
    
    def update_effects(self):
        """Update effect timers"""
        if self.effect_duration > 0:
            self.effect_duration -= 1
            if self.effect_duration <= 0:
                self.action_effect = None
    
    def is_valid_model_position(self, pos):
        """Check if a model position maintains unit cohesion"""
        for existing_pos in self.model_positions:
            if self.distance_between(pos, existing_pos) <= 1.0:
                return True
        return False
    
    def distance_between(self, pos1, pos2):
        """Calculate distance between two positions"""
        return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)
    
    def quality_test(self, modifier=0):
        # Phase 3: Sergeant bonus
        if self.has_sergeant:
            modifier += 1
            
        roll = random.randint(1, 6)
        if roll == 6:
            return True
        if roll == 1:
            return False
        return roll + modifier >= self.quality
    
    def defense_test(self, modifier=0):
        roll = random.randint(1, 6)
        if roll == 6:
            return True
        if roll == 1:
            return False
        return roll + modifier >= self.defense
    
    def can_fly(self):
        """Check if unit can fly"""
        return "Flying" in self.special_rules
    
    def can_strider(self):
        """Check if unit ignores difficult terrain"""
        return "Strider" in self.special_rules
    
    def move(self, action, target_pos=None, target_elevation=0):
        if self.shaken:
            return False, "Unit is shaken"
        
        move_distance = self.move_types[action]
        
        # Phase 3: Musician bonus (simplified - affects all friendly units)
        musician_bonus = 1 if any(u.has_musician and u.player_id == self.player_id for u in [self]) else 0
        
        # Apply movement modifiers
        if "Fast" in self.special_rules:
            if action == Action.ADVANCE:
                move_distance += 2 + musician_bonus
            elif action in [Action.RUSH, Action.CHARGE]:
                move_distance += 4 + musician_bonus
        elif "Slow" in self.special_rules:
            if action == Action.ADVANCE:
                move_distance = max(0, move_distance - 2 + musician_bonus)
            elif action in [Action.RUSH, Action.CHARGE]:
                move_distance = max(0, move_distance - 4 + musician_bonus)
        else:
            move_distance += musician_bonus
        
        if target_pos:
            distance = self.distance_between(self.position, target_pos)
            elevation_change = abs(target_elevation - self.elevation)
            
            # Check if movement requires jumping
            if elevation_change > 1 and not self.can_fly():
                return self.attempt_jump(target_pos, target_elevation, move_distance)
            
            # Flying units ignore terrain and elevation
            if self.can_fly():
                if distance <= move_distance:
                    self.set_position(target_pos, target_elevation)
                    return True, "Flying movement successful"
                else:
                    # Move as far as possible toward target
                    ratio = move_distance / distance
                    new_x = self.position[0] + (target_pos[0] - self.position[0]) * ratio
                    new_y = self.position[1] + (target_pos[1] - self.position[1]) * ratio
                    new_pos = (round(new_x), round(new_y))
                    self.set_position(new_pos, self.elevation)
                    return True, "Partial flying movement"
            
            # Ground movement with terrain effects
            effective_distance = distance
            if not self.can_strider():
                # Check for difficult terrain (simplified - affects whole move if any part crosses it)
                pass
            
            if effective_distance <= move_distance:
                self.set_position(target_pos, target_elevation)
                return True, "Movement successful"
            else:
                # Move as far as possible
                ratio = move_distance / effective_distance
                new_x = self.position[0] + (target_pos[0] - self.position[0]) * ratio
                new_y = self.position[1] + (target_pos[1] - self.position[1]) * ratio
                new_pos = (round(new_x), round(new_y))
                self.set_position(new_pos, self.elevation)
                return True, "Partial movement"
        
        return True, "No movement"
    
    def attempt_jump(self, target_pos, target_elevation, move_distance):
        """Attempt to jump to higher elevation"""
        distance = self.distance_between(self.position, target_pos)
        elevation_change = target_elevation - self.elevation
        
        if distance > move_distance:
            return False, "Target too far to jump"
        
        # Jump test - need 3+ on dice equal to distance in 3" increments
        dice_needed = max(1, int(distance / 3) + 1)
        successes = 0
        
        for _ in range(dice_needed):
            if random.randint(1, 6) >= 3:
                successes += 1
        
        if successes == dice_needed:
            self.set_position(target_pos, target_elevation)
            return True, f"Successful jump (rolled {successes}/{dice_needed})"
        else:
            # Failed jump - take falling damage
            fall_damage = max(1, int(elevation_change / 3))
            self.take_falling_damage(fall_damage)
            return False, f"Jump failed ({successes}/{dice_needed}) - took {fall_damage} falling damage"
    
    def take_falling_damage(self, damage):
        """Take damage from falling"""
        hits = damage
        ap = max(1, int(damage / 3))  # AP(1) per full 3" fallen
        
        result = self.take_hits(hits, ap)
        if result == WoundEffect.KNOCKED_OUT:
            return f"Destroyed by fall!"
        elif result == WoundEffect.SHAKEN:
            return f"Shaken by fall!"
        return f"Survived fall with {hits} wounds"
    
    def has_line_of_sight(self, target, game):
        """Check if unit has line of sight to target"""
        # Simplified LOS - Flying units always have LOS
        if self.can_fly() or target.can_fly():
            return True
        
        # Check elevation difference
        elevation_diff = abs(self.elevation - target.elevation)
        if elevation_diff > 2:  # Can see over obstacles if elevation advantage
            return True
        
        # Basic LOS check (in full game would trace line)
        return True
    
    def get_cover_bonus(self, game):
        """Get defense bonus from cover"""
        in_cover = 0
        for model_pos in self.model_positions:
            terrain = game.get_terrain_at(model_pos)
            if terrain == TerrainType.COVER:
                in_cover += 1
        
        if in_cover > len(self.model_positions) // 2:
            return 1
        return 0
    
    def shoot(self, targets, weapons_to_use, game):
        """Enhanced shooting with multiple targets"""
        if self.shaken:
            return {}
        
        results = {}
        
        for i, (target, weapon) in enumerate(zip(targets, weapons_to_use)):
            if not target or not weapon:
                continue
                
            # Show ranged attack effect
            target.apply_action_effect('R', 2)
            
            # Check weapon type and range
            if weapon.weapon_type == WeaponType.INDIRECT:
                # Indirect weapons ignore LOS but get -1 to hit after moving
                hit_modifier = -1 if self.activated else 0
                can_shoot = True
            else:
                # Check range and LOS for direct weapons
                min_distance = self.get_min_distance_to_target(target)
                if min_distance > weapon.range:
                    results[f"Target {i+1}"] = f"Out of range ({min_distance:.1f}>{weapon.range})"
                    continue
                
                if not self.has_line_of_sight(target, game):
                    results[f"Target {i+1}"] = "No line of sight"
                    continue
                
                hit_modifier = 0
                can_shoot = True
            
            if not can_shoot:
                continue
            
            # Apply stealth modifier
            if "Stealth" in target.special_rules:
                min_distance = self.get_min_distance_to_target(target)
                if min_distance > 9:
                    hit_modifier -= 1
            
            hits = 0
            hit_rolls = []
            
            for attack in range(weapon.attacks):
                if "Reliable" in weapon.special_rules:
                    roll = random.randint(1, 6)
                    hit_rolls.append(roll)
                    if roll >= 2 or roll == 6:
                        hits += 1
                        
                        # Rending - 6s get AP(4)
                        if "Rending" in weapon.special_rules and roll == 6:
                            weapon.temp_ap = 4
                else:
                    roll = random.randint(1, 6)
                    hit_rolls.append(roll)
                    if roll == 6 or (roll >= self.quality + hit_modifier and roll != 1):
                        hits += 1
                        
                        # Rending check
                        if "Rending" in weapon.special_rules and roll == 6:
                            weapon.temp_ap = 4
            
            if hits > 0:
                # Show hit effect
                target.apply_action_effect('A', 3)  # Attack effect
                
                # Phase 3: Check for Blast weapons
                if "Blast" in weapon.special_rules:
                    damage_result = self.resolve_blast_attack(target, weapon, hits, game)
                else:
                    damage_result = self.resolve_weapon_hits(target, weapon, hits, game)
                results[f"Target {i+1}"] = f"{hits} hits from {weapon.name}: {damage_result}"
            else:
                results[f"Target {i+1}"] = f"No hits from {weapon.name} (rolls: {hit_rolls})"
        
        return results
    
    def resolve_blast_attack(self, target, weapon, hits, game):
        """Phase 3: Resolve Blast(X) weapons"""
        blast_value = weapon.special_rules["Blast"]
        
        # Find all units within 3" of target
        affected_units = []
        for unit in game.units:
            if game.distance(unit.position, target.position) <= 3:
                affected_units.append(unit)
                # Show blast effect on all units in area
                unit.apply_action_effect('*', 3)  # Blast effect
        
        # Multiply hits (up to enemy models in area)
        enemy_models = sum(u.models for u in affected_units if u.player_id != self.player_id)
        multiplier = min(blast_value, enemy_models) if enemy_models > 0 else 1
        total_hits = hits * multiplier
        
        # Split hits evenly between affected units
        results = []
        if affected_units:
            hits_per_unit = total_hits // len(affected_units)
            remainder = total_hits % len(affected_units)
            
            for i, unit in enumerate(affected_units):
                unit_hits = hits_per_unit + (1 if i < remainder else 0)
                if unit_hits > 0:
                    # Blast ignores cover
                    base_ap = weapon.special_rules.get("AP", 0)
                    temp_ap = getattr(weapon, 'temp_ap', 0)
                    total_ap = base_ap + temp_ap
                    weapon.temp_ap = 0
                    
                    wound_effect = unit.take_hits(unit_hits, total_ap, 0)  # 0 cover bonus
                    results.append(f"{unit.name}: {unit_hits} blast hits")
        
        return f"BLAST({blast_value}): " + "; ".join(results)
    
    def get_min_distance_to_target(self, target):
        """Get minimum distance to target unit"""
        min_distance = float('inf')
        for model_pos in self.model_positions:
            for target_pos in target.model_positions:
                distance = self.distance_between(model_pos, target_pos)
                min_distance = min(min_distance, distance)
        return min_distance
    
    def resolve_weapon_hits(self, target, weapon, hits, game):
        """Resolve weapon hits with special rules"""
        cover_bonus = target.get_cover_bonus(game)
        base_ap = weapon.special_rules.get("AP", 0)
        
        # Check for temporary AP from Rending
        temp_ap = getattr(weapon, 'temp_ap', 0)
        total_ap = base_ap + temp_ap
        weapon.temp_ap = 0  # Reset after use
        
        # Phase 3: Check for Deadly weapons
        if "Deadly" in weapon.special_rules:
            return self.resolve_deadly_hits(target, weapon, hits, total_ap, cover_bonus)
        
        # Apply Poison effects
        if "Poison" in weapon.special_rules:
            # Poison forces re-rolls of natural 6s on defense
            poison_hits = hits
            target.add_status_effect('POISONED')
        else:
            poison_hits = 0
        
        wound_effect = target.take_hits(hits, total_ap, cover_bonus, poison_hits)
        
        result_msg = ""
        if cover_bonus > 0:
            result_msg += "(target in cover) "
        if temp_ap > 0:
            result_msg += f"(AP {total_ap} from rending) "
        if poison_hits > 0:
            result_msg += "(poison) "
        
        if wound_effect == WoundEffect.KNOCKED_OUT:
            target.add_status_effect('UNCONSCIOUS')
            result_msg += f"{target.name} destroyed!"
        elif wound_effect == WoundEffect.SHAKEN:
            target.add_status_effect('SHAKEN')
            result_msg += f"{target.name} shaken!"
        elif target.wound_markers > 0:
            result_msg += f"{target.name} takes wounds"
        else:
            result_msg += "no effect"
        
        return result_msg
    
    def resolve_deadly_hits(self, target, weapon, hits, ap, cover_bonus):
        """Phase 3: Resolve Deadly(X) weapons"""
        deadly_value = weapon.special_rules["Deadly"]
        
        # Each hit becomes X wounds, assigned to specific models
        total_wounds = hits * deadly_value
        
        models_killed = 0
        remaining_wounds = 0
        
        if target.models > 1:
            # Kill models first
            models_killed = min(total_wounds, target.models - 1)
            target.models -= models_killed
            remaining_wounds = total_wounds - models_killed
            
            # Apply remaining wounds to last model
            if remaining_wounds > 0 and target.models > 0:
                target.wound_markers += remaining_wounds
                wound_effect = target.check_wound_effects()
            else:
                wound_effect = WoundEffect.NONE
        else:
            # Single model takes all wounds
            target.wound_markers += total_wounds
            wound_effect = target.check_wound_effects()
        
        result = f"DEADLY({deadly_value}): {hits} hits = {total_wounds} wounds"
        if models_killed > 0:
            result += f", killed {models_killed} models"
        if wound_effect == WoundEffect.KNOCKED_OUT:
            target.add_status_effect('UNCONSCIOUS')
            result += f", {target.name} destroyed!"
        elif wound_effect == WoundEffect.SHAKEN:
            target.add_status_effect('SHAKEN')
            result += f", {target.name} shaken!"
        
        return result
    
    def fight_in_melee(self, target, is_charging=False, is_counter=False):
        """Enhanced melee combat with Impact and special rules"""
        if self.shaken:
            return 0, []
        
        # Show melee attack effect
        target.apply_action_effect('A', 3)
        
        total_hits = 0
        combat_log = []
        
        # Impact hits when charging (before regular attacks)
        if is_charging and not self.fatigued:
            for weapon in self.weapons:
                if weapon.is_melee and "Impact" in weapon.special_rules:
                    impact_value = weapon.special_rules["Impact"]
                    impact_hits = 0
                    impact_rolls = []
                    
                    for _ in range(impact_value):
                        roll = random.randint(1, 6)
                        impact_rolls.append(roll)
                        if roll >= 2:  # Impact hits on 2+
                            impact_hits += 1
                    
                    if impact_hits > 0:
                        total_hits += impact_hits
                        combat_log.append(f"Impact: {impact_hits} hits (rolls: {impact_rolls})")
        
        # Regular melee attacks
        for weapon in self.weapons:
            if weapon.is_melee:
                modifier = 0
                
                # Lance bonus when charging
                if is_charging and "Lance" in weapon.special_rules:
                    modifier = 1
                
                weapon_hits = 0
                for _ in range(weapon.attacks):
                    if self.quality_test(modifier):
                        weapon_hits += 1
                
                total_hits += weapon_hits
                combat_log.append(f"{weapon.name}: {weapon_hits} hits")
        
        if not is_counter:
            self.fatigued = True
        
        return total_hits, combat_log
    
    def can_counter(self):
        """Check if unit can counter-attack when charged"""
        for weapon in self.weapons:
            if weapon.is_melee and "Counter" in weapon.special_rules:
                return True
        return False
    
    def take_hits(self, hits, ap=0, cover_bonus=0, poison_hits=0):
        """Enhanced hit resolution with group wounds and special effects"""
        if hits == 0:
            return WoundEffect.NONE
        
        wounds_dealt = 0
        models_killed = 0
        
        # Process each hit individually for multi-model units
        for hit in range(hits):
            # Defense roll with modifiers
            defense_modifier = cover_bonus - ap
            
            # Poison forces re-roll of natural 6s
            is_poison_hit = hit < poison_hits
            
            if is_poison_hit:
                roll = random.randint(1, 6)
                if roll == 6:  # Re-roll natural 6s for poison
                    roll = random.randint(1, 6)
                if roll == 6 or roll + defense_modifier >= self.defense:
                    continue  # Hit blocked
            else:
                if self.defense_test(defense_modifier):
                    continue  # Hit blocked
            
            # Hit gets through - apply to unit
            if self.models > 1:
                # Multi-model unit: kill models until only last remains
                models_killed += 1
                self.models -= 1
                if len(self.model_positions) > 1:
                    self.model_positions.pop()
                
                # If this was the last extra model, remaining hits wound the final model
                if self.models == 1:
                    break
            else:
                # Single model or last model: accumulate wounds
                wounds_dealt += 1
        
        # Apply any remaining hits as wounds to the last model
        remaining_hits = hits - models_killed
        if remaining_hits > 0 and self.models == 1:
            for _ in range(remaining_hits):
                if not (poison_hits > 0 and self.defense_test(cover_bonus - ap)):
                    wounds_dealt += 1
        
        # Check for regeneration
        if "Regeneration" in self.special_rules and wounds_dealt > 0:
            regenerated = 0
            for _ in range(wounds_dealt):
                if random.randint(1, 6) >= 5:
                    regenerated += 1
            wounds_dealt -= regenerated
            if regenerated > 0:
                print(f"  {self.name} regenerated {regenerated} wounds!")
        
        # Apply wounds and check effects
        if wounds_dealt > 0:
            self.wound_markers += wounds_dealt
            return self.check_wound_effects()
        
        return WoundEffect.NONE
    
    def check_wound_effects(self):
        """Check wound effects with pushing"""
        if self.wound_markers < self.tough:
            return WoundEffect.NONE
            
        roll = random.randint(1, 6) + self.wound_markers
        
        if roll >= 6 + self.tough - 1:
            return WoundEffect.KNOCKED_OUT
        else:
            self.shaken = True
            return WoundEffect.SHAKEN
    
    def try_push(self, attacker, game):
        """Try to push shaken unit"""
        if not self.shaken:
            return False
        
        roll = random.randint(1, 6)
        if roll >= 4:
            # Calculate push direction (away from attacker)
            dx = self.position[0] - attacker.position[0]
            dy = self.position[1] - attacker.position[1]
            distance = math.sqrt(dx**2 + dy**2)
            
            if distance > 0:
                # Normalize and push 2"
                push_distance = 2
                new_x = self.position[0] + (dx / distance) * push_distance
                new_y = self.position[1] + (dy / distance) * push_distance
                
                # Clamp to board boundaries
                new_x = max(0, min(game.grid_size - 1, round(new_x)))
                new_y = max(0, min(game.grid_size - 1, round(new_y)))
                
                old_pos = self.position
                self.set_position((new_x, new_y), self.elevation)
                return f"Pushed from {old_pos} to {self.position}"
        
        return False
    
    def morale_test(self, hero_quality=None):
        """Phase 3: Enhanced morale with Hero command"""
        test_quality = self.quality
        
        # Use hero quality if better and within range
        if hero_quality and hero_quality < test_quality:
            test_quality = hero_quality
        
        # Phase 3: Banner bonus
        modifier = 1 if self.has_banner else 0
        
        if "Fearless" in self.special_rules:
            roll = random.randint(1, 6)
            if roll + modifier < test_quality:
                return random.randint(1, 6) >= 4
            return True
        
        roll = random.randint(1, 6)
        if roll == 6:
            return True
        if roll == 1:
            return False
        return roll + modifier >= test_quality
    
    def cast_spell(self, spell_name, target, game):
        """Phase 3: Cast spell if enough tokens"""
        if "Caster" not in self.special_rules:
            return False, "Unit cannot cast spells"
        
        spell_costs = {"Fireball": 3, "Lightning": 2, "Heal": 1, "Curse": 1}
        cost = spell_costs.get(spell_name, 1)
        
        if self.spell_tokens < cost:
            return False, f"Need {cost} spell tokens, have {self.spell_tokens}"
        
        # Show spell casting effect
        target.apply_action_effect('S', 3)
        
        # Roll to cast
        roll = random.randint(1, 6)
        if roll >= 4:
            self.spell_tokens -= cost
            effect = self.resolve_spell_effect(spell_name, target, game)
            return True, f"Cast {spell_name}: {effect}"
        else:
            self.spell_tokens -= cost  # Tokens spent even if failed
            return False, f"Failed to cast {spell_name} (rolled {roll})"
    
    def resolve_spell_effect(self, spell_name, target, game):
        """Resolve spell effects"""
        if spell_name == "Fireball":
            # Area damage around target
            affected = 0
            for unit in game.units:
                if game.distance(unit.position, target.position) <= 3:
                    unit.take_hits(2, 1)  # 2 hits with AP(1)
                    unit.add_status_effect('BURNING')
                    unit.apply_action_effect('*', 4)  # Show blast effect
                    affected += 1
            return f"Fireball affects {affected} units within 3\""
        elif spell_name == "Lightning":
            wound_effect = target.take_hits(4, 2)
            return f"Lightning strikes {target.name} for 4 hits AP(2)"
        elif spell_name == "Heal":
            healed = min(3, target.wound_markers)
            target.wound_markers -= healed
            target.remove_status_effect('POISONED')
            target.remove_status_effect('BURNING')
            return f"Healed {healed} wounds on {target.name}"
        elif spell_name == "Curse":
            target.shaken = True
            target.add_status_effect('SHAKEN')
            return f"{target.name} cursed and shaken"
        return "Spell effect applied"
    
    def __str__(self):
        model_count = f"({self.models})" if self.models > 1 else ""
        status = f"{self.name}{model_count} at {self.position}"
        if self.elevation > 0:
            status += f" (elev {self.elevation})"
        if self.shaken:
            status += " [SHAKEN]"
        if self.fatigued:
            status += " [FATIGUED]"
        if self.wound_markers > 0:
            status += f" [{self.wound_markers} wound(s)]"
        
        # Phase 3: Show spell tokens
        if self.spell_tokens > 0:
            status += f" [{self.spell_tokens} spells]"
        
        # Phase 3: Show command group
        commands = []
        if self.has_sergeant:
            commands.append("SGT")
        if self.has_musician:
            commands.append("MUS")
        if self.has_banner:
            commands.append("BAN")
        if commands:
            status += f" [{','.join(commands)}]"
        
        # Show status effects
        if self.status_effects:
            effects = list(self.status_effects)
            status += f" [Effects: {','.join(effects)}]"
        
        return status

class Weapon:
    def __init__(self, name, attacks, range, is_melee=False, weapon_type=None, special_rules=None):
        self.name = name
        self.attacks = attacks
        self.range = range
        self.is_melee = is_melee
        self.weapon_type = weapon_type if weapon_type else (WeaponType.MELEE if is_melee else WeaponType.RANGED)
        self.special_rules = special_rules if special_rules else {}
        self.temp_ap = 0  # For rending effects

class Game:
    def __init__(self, grid_size=20):
        self.grid_size = grid_size
        self.grid = [[TerrainType.NORMAL for _ in range(grid_size)] for _ in range(grid_size)]
        self.elevation_map = [[0 for _ in range(grid_size)] for _ in range(grid_size)]  # Height map
        self.units = []
        self.objectives = []
        self.players = ["Player 1", "Player 2"]
        self.current_player = 0
        self.round = 1
        self.frames = []  # Store each frame for slideshow
        self.add_terrain()
        
    def add_terrain(self):
        """Add terrain including elevation"""
        # Add standard terrain
        for i in range(5):
            x, y = random.randint(0, self.grid_size-1), random.randint(0, self.grid_size-1)
            terrain_type = random.choice([TerrainType.COVER, TerrainType.DIFFICULT, TerrainType.DANGEROUS])
            self.grid[y][x] = terrain_type
            
            # Make terrain areas
            for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.grid_size and 0 <= ny < self.grid_size:
                    self.grid[ny][nx] = terrain_type
        
        # Add some elevated terrain
        for i in range(3):
            x, y = random.randint(2, self.grid_size-3), random.randint(2, self.grid_size-3)
            height = random.randint(1, 3)
            
            # Create hill
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < self.grid_size and 0 <= ny < self.grid_size:
                        self.elevation_map[ny][nx] = height
    
    def get_elevation_at(self, position):
        """Get elevation at position"""
        x, y = position
        if 0 <= x < self.grid_size and 0 <= y < self.grid_size:
            return self.elevation_map[y][x]
        return 0
    
    def add_unit(self, unit, position):
        elevation = self.get_elevation_at(position)
        unit.set_position(position, elevation)
        self.units.append(unit)
    
    def add_objective(self, position):
        self.objectives.append({
            "position": position, 
            "controlled_by": None,
            "contested": False
        })
    
    def distance(self, pos1, pos2):
        return math.sqrt((pos1[0]-pos2[0])**2 + (pos1[1]-pos2[1])**2)
    
    def get_unit_at(self, position):
        for unit in self.units:
            for model_pos in unit.model_positions:
                if model_pos == position:
                    return unit
        return None
    
    def get_terrain_at(self, position):
        x, y = position
        if 0 <= x < self.grid_size and 0 <= y < self.grid_size:
            return self.grid[y][x]
        return TerrainType.NORMAL
    
    def capture_frame(self, title="", action_text=""):
        """Capture current game state as a frame"""
        frame_text = self.get_display_text(title, action_text)
        self.frames.append(frame_text)
        
    def get_display_text(self, title="", action_text=""):
        """UNIFIED display system - used for both console and image generation"""
        lines = []
        
        if title:
            lines.append("=" * 75)
            lines.append(title)
            lines.append("=" * 75)
        
        lines.append(f"Round {self.round} - Player 1 vs Player 2 - {self.players[self.current_player]}'s Turn")
        lines.append("=" * 75)
        
        # Legend
        lines.append("LEGEND: 1=P1  2=P2  O=Objective  C=Contested  H=Hero")
        lines.append("        #=Cover  ~=Difficult  !=Dangerous  ^=Elevated")
        lines.append("        S=Sergeant  M=Musician  N=Banner")
        lines.append("")
        lines.append("ACTION SYMBOLS: A=Attack  S=Spell  R=Ranged  *=Blast")
        lines.append("STATUS EFFECTS: U=Unconscious  P=Poisoned  K=Shaken  B=Burning")
        lines.append("-" * 75)
        lines.append("PHASE 3 FEATURES: Magic, Blast weapons, Command groups")
        lines.append("Hero command, Deadly weapons, Enhanced morale")
        lines.append("-" * 75)
        
        # Grid
        top_labels = " ".join(f"{i % 10}" for i in range(self.grid_size))
        lines.append(f"    {top_labels}")
        lines.append("   +" + "-" * (self.grid_size * 2 - 1) + "+")
        
        # Create display grid
        display_grid = [['.' for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        
        # Add terrain and elevation
        for y in range(self.grid_size):
            for x in range(self.grid_size):
                elevation = self.get_elevation_at((x, y))
                terrain = self.get_terrain_at((x, y))
                
                if elevation > 0:
                    display_grid[y][x] = '^'
                elif terrain == TerrainType.COVER:
                    display_grid[y][x] = '#'
                elif terrain == TerrainType.DIFFICULT:
                    display_grid[y][x] = '~'
                elif terrain == TerrainType.DANGEROUS:
                    display_grid[y][x] = '!'
        
        # Add objectives
        for obj in self.objectives:
            x, y = obj["position"]
            if obj["contested"]:
                display_grid[y][x] = 'C'
            else:
                display_grid[y][x] = 'O'
        
        # Add units
        for unit in self.units:
            for model_pos in unit.model_positions:
                x, y = model_pos
                if 0 <= x < self.grid_size and 0 <= y < self.grid_size:
                    display_grid[y][x] = unit.get_display_symbol()
        
        for y in range(self.grid_size):
            row = f"{y % 10} |"
            for x in range(self.grid_size):
                row += display_grid[y][x] + " "
            row += "|"
            lines.append(row)
        
        lines.append("   +" + "-" * (self.grid_size * 2 - 1) + "+")
        lines.append(f"    {top_labels}")
        
        # Units status - FIXED to show actual map symbols
        lines.append("")
        lines.append("UNITS:")
        player1_units = [u for u in self.units if u.player_id == 0]
        player2_units = [u for u in self.units if u.player_id == 1]
        
        lines.append("Player 1:")
        for unit in player1_units:
            special_rules = ", ".join(unit.special_rules.keys())
            symbol = unit.get_display_symbol()
            lines.append(f"  {symbol}: {unit} - {special_rules}")
        
        lines.append("")
        lines.append("Player 2:")
        for unit in player2_units:
            special_rules = ", ".join(unit.special_rules.keys())
            symbol = unit.get_display_symbol()
            lines.append(f"  {symbol}: {unit} - {special_rules}")
        
        # Objectives
        lines.append("")
        lines.append("OBJECTIVES:")
        for i, obj in enumerate(self.objectives):
            status = "Contested" if obj["contested"] else "Uncontrolled"
            if obj["controlled_by"] and not obj["contested"]:
                status = f"Player {obj['controlled_by'].player_id + 1}"
            elevation = self.get_elevation_at(obj["position"])
            elev_str = f" (elev {elevation})" if elevation > 0 else ""
            lines.append(f"  {i + 1}: at {obj['position']}{elev_str} - {status}")
        
        lines.append("")
        lines.append("ACTIONS: Hold(0) | Advance(1) | Rush(2) | Charge(3)")
        lines.append("PHASE 3: Cast spells, Blast weapons, Command bonuses")
        lines.append("=" * 75)
        
        if action_text:
            lines.append("")
            lines.append(f"ACTION: {action_text}")
        
        return "\n".join(lines)
    
    def create_slide_image(self, text, slide_num):
        """Convert text to a slide image using Courier New font"""
        try:
            # Image dimensions
            width, height = 1920, 1080
            
            # Create image with white background
            img = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(img)
            
            # Try to load Courier New, fallback to default monospace
            try:
                font = ImageFont.truetype("cour.ttf", 14)  # Windows
            except:
                try:
                    font = ImageFont.truetype("/System/Library/Fonts/Courier.ttc", 14)  # Mac
                except:
                    try:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)  # Linux
                    except:
                        font = ImageFont.load_default()
            
            # Draw text
            y_offset = 20
            for line in text.split('\n'):
                # Color coding for white background - keep original bright colors
                color = 'black'  # Default text color
                
                # Color player unit lines and grid lines with units
                if 'Player 1' in line and ':' in line:
                    color = '#ff4444'  # Keep bright red for Player 1
                elif 'Player 2' in line and ':' in line:
                    color = '#4444ff'  # Keep bright blue for Player 2
                elif line.startswith('ACTION:'):
                    color = '#cc4400'  # Dark orange for actions (visible on white)
                elif '>>>' in line:
                    color = '#ff6600'  # Keep orange for action progress
                
                # Handle grid lines character by character to color units
                if '|' in line and any(c in line for c in ['1', '2', 'H', 'M', 'S', 'N', 'A', 'R', '*']):
                    # This is a grid line with units - draw character by character
                    x_offset = 20
                    for char in line:
                        char_color = 'black'  # Default
                        if char in ['1', 'H']:  # Player 1 units and heroes
                            char_color = '#ff4444'  # Bright red
                        elif char in ['2']:  # Player 2 units
                            char_color = '#4444ff'  # Bright blue
                        elif char in ['S', 'M', 'N']:  # Command units - color by context
                            # Need to determine which player they belong to
                            # For now, use purple to distinguish command units
                            char_color = '#8800cc'  # Purple for command
                        elif char in ['A', 'R', '*']:  # Action symbols
                            char_color = '#cc4400'  # Dark orange, visible on white
                        elif char == 'S' and 'spell' in line.lower():  # Spell symbols
                            char_color = '#8800cc'  # Dark purple for spells
                        
                        draw.text((x_offset, y_offset), char, fill=char_color, font=font)
                        x_offset += 8  # Approximate character width
                else:
                    # Regular line - draw normally with line color
                    draw.text((20, y_offset), line, fill=color, font=font)
                
                y_offset += 16
                
                if y_offset > height - 40:
                    break
            
            # Save slide
            img.save(f'slide_{slide_num:03d}.png')
            return True
            
        except Exception as e:
            print(f"Error creating slide {slide_num}: {e}")
            return False
    
    def generate_slideshow(self):
        """Generate all slides from captured frames"""
        print(f"Generating {len(self.frames)} slides...")
        
        for i, frame_text in enumerate(self.frames):
            if self.create_slide_image(frame_text, i + 1):
                print(f"Created slide_{i+1:03d}.png")
        
        print(f"\nSlideshow complete! Generated {len(self.frames)} slides.")
        print("To create GIF, run: convert -delay 33 slide_*.png combat.gif")
        print("(Requires ImageMagick installed)")
        
    def save_frames_as_text(self):
        """Save all frames as text files"""
        for i, frame_text in enumerate(self.frames):
            with open(f'frame_{i+1:03d}.txt', 'w') as f:
                f.write(frame_text)
        print(f"Saved {len(self.frames)} text frames.")
    
    def display_grid(self, show_action_frame=False):
        # Capture frame for slideshow using UNIFIED system
        if show_action_frame:
            self.capture_frame(">>> ACTION IN PROGRESS <<<")
        else:
            self.capture_frame()
        
        # Console display using the SAME unified system
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Get the unified display text
        display_text = self.get_display_text(
            ">>> ACTION IN PROGRESS <<<" if show_action_frame else ""
        )
        
        # Print with console colors
        for line in display_text.split('\n'):
            # Apply console colors to specific content
            colored_line = line
            
            # Color player sections
            if 'Player 1' in line:
                colored_line = line.replace('Player 1', f'{Colors.RED}Player 1{Colors.END}')
            elif 'Player 2' in line:
                colored_line = line.replace('Player 2', f'{Colors.BLUE}Player 2{Colors.END}')
            
            # Color action progress
            if '>>>' in line:
                colored_line = f"{Colors.BOLD}{Colors.YELLOW}{line}{Colors.END}"
            
            # Color grid lines with units (character by character for proper coloring)
            if '|' in line and any(c in line for c in ['1', '2', 'H', 'M', 'S', 'N', 'A', 'R', '*']):
                colored_chars = []
                for char in line:
                    if char in ['1', 'H']:  # Player 1 units and heroes
                        colored_chars.append(f'{Colors.RED}{char}{Colors.END}')
                    elif char == '2':  # Player 2 units
                        colored_chars.append(f'{Colors.BLUE}{char}{Colors.END}')
                    elif char in ['S', 'M', 'N']:  # Command units
                        colored_chars.append(f'{Colors.BOLD}{char}{Colors.END}')
                    elif char == 'A':  # Attack
                        colored_chars.append(f'{Colors.YELLOW}{char}{Colors.END}')
                    elif char == 'R':  # Ranged
                        colored_chars.append(f'{Colors.CYAN}{char}{Colors.END}')
                    elif char == '*':  # Blast
                        colored_chars.append(f'{Colors.GREEN}{char}{Colors.END}')
                    elif char == 'S' and any(c in line for c in ['spell', 'magic']):  # Spells
                        colored_chars.append(f'{Colors.PURPLE}{char}{Colors.END}')
                    else:
                        colored_chars.append(char)
                colored_line = ''.join(colored_chars)
            
            print(colored_line)
        
        print(f"Frame {len(self.frames)} captured for slideshow")
        
        if show_action_frame:
            time.sleep(1.5)  # Show action frame for 1.5 seconds
    
    def update_unit_effects(self):
        """Update all unit visual effects"""
        for unit in self.units:
            unit.update_effects()
            
            # Update status effects based on unit state
            if unit.shaken and 'SHAKEN' not in unit.status_effects:
                unit.add_status_effect('SHAKEN')
            elif not unit.shaken and 'SHAKEN' in unit.status_effects:
                unit.remove_status_effect('SHAKEN')
    
    def activate_unit(self, unit, action, target_pos=None, target_units=None, target_elevation=0):
        """Enhanced activation with Phase 3 features and visual effects"""
        if unit.activated:
            return False, "Unit already activated this round"
            
        unit.activated = True
        
        if action == Action.HOLD:
            if target_units:
                # Apply action effects BEFORE capturing frame
                for target in target_units:
                    if target:
                        target.apply_action_effect('R', 2, unit.player_id)  # Ranged attack from this unit's player
                
                # Capture frame showing ranged effects
                self.capture_frame("", f"War Cannons targeting enemies with ranged fire!")
                
                # Can shoot at up to 2 targets with different weapon types
                weapons_to_use = []
                ranged_weapons = [w for w in unit.weapons if not w.is_melee]
                
                # Assign weapons to targets (simplified)
                for i, target in enumerate(target_units[:2]):
                    if i < len(ranged_weapons):
                        weapons_to_use.append(ranged_weapons[i])
                    else:
                        weapons_to_use.append(None)
                
                results = unit.shoot(target_units, weapons_to_use, self)
                
                # Capture frame after shooting (showing hit effects)
                self.capture_frame("", f"Shooting results visible on battlefield")
                
                result_msg = f"{unit.name} holds and shoots: "
                for target_num, result in results.items():
                    result_msg += f"{target_num}: {result}; "
                
                # Handle pushing shaken units
                for target in target_units:
                    if target and target.shaken:
                        push_result = target.try_push(unit, self)
                        if push_result:
                            result_msg += f" {target.name} pushed!"
                
                return True, result_msg.rstrip('; ')
            return True, f"{unit.name} holds position"
            
        elif action == Action.ADVANCE:
            old_pos = unit.position
            success, move_msg = unit.move(action, target_pos, target_elevation)
            if success:
                # Capture frame showing movement
                self.capture_frame("", f"{unit.name} advances from {old_pos} to {unit.position}")
                
                result_msg = f"{unit.name} advances: {move_msg}"
                if target_units:
                    # Apply ranged effects and capture
                    for target in target_units:
                        if target:
                            target.apply_action_effect('R', 2)
                    
                    self.capture_frame("", f"{unit.name} shoots after advancing")
                    
                    # Can shoot after advancing
                    weapons_to_use = []
                    ranged_weapons = [w for w in unit.weapons if not w.is_melee]
                    
                    for i, target in enumerate(target_units[:2]):
                        if i < len(ranged_weapons):
                            weapons_to_use.append(ranged_weapons[i])
                        else:
                            weapons_to_use.append(None)
                    
                    shoot_results = unit.shoot(target_units, weapons_to_use, self)
                    
                    # Capture post-shooting frame
                    self.capture_frame("", f"After shooting - effects visible")
                    
                    for target_num, result in shoot_results.items():
                        result_msg += f"; {target_num}: {result}"
                
                return True, result_msg
            return False, f"Advance failed: {move_msg}"
            
        elif action == Action.RUSH:
            old_pos = unit.position
            success, move_msg = unit.move(action, target_pos, target_elevation)
            if success:
                # Capture frame showing rush movement
                self.capture_frame("", f"{unit.name} rushes from {old_pos} to {unit.position}")
                return True, f"{unit.name} rushes: {move_msg}"
            return False, f"Rush failed: {move_msg}"
            
        elif action == Action.CHARGE:
            if not target_units or not target_units[0]:
                return False, "Charge requires a target unit"
                
            target_unit = target_units[0]
            old_pos = unit.position
            
            # Check if can reach target
            min_distance = unit.get_min_distance_to_target(target_unit)
            move_distance = unit.move_types[action]
            
            if "Fast" in unit.special_rules:
                move_distance += 4
            elif "Slow" in unit.special_rules:
                move_distance = max(0, move_distance - 4)
            
            if min_distance > move_distance:
                return False, f"Target out of charge range ({min_distance:.1f}>{move_distance})"
                
            # Move into base contact
            target_pos = target_unit.position
            target_elevation = target_unit.elevation
            unit.set_position(target_pos, target_elevation)
            
            # Capture charge movement frame
            self.capture_frame("", f"{unit.name} charges from {old_pos} into melee!")
            
            # Apply melee effect to target
            target_unit.apply_action_effect('A', 3)
            
            # Capture melee contact frame
            self.capture_frame("", f"Melee combat engaged!")
            
            # Resolve melee combat
            result = self.resolve_melee(unit, target_unit)
            
            # Capture post-combat frame
            self.capture_frame("", f"After melee combat - casualties taken")
            
            return True, f"{unit.name} charges {target_unit.name}: {result}"
            
        return False, "Unknown action"
    
    def resolve_melee(self, attacker, defender):
        """Enhanced melee with Phase 3 features"""
        result_parts = []
        
        # Check for counter-attacks (strike first)
        if defender.can_counter() and not defender.shaken:
            counter_hits, counter_log = defender.fight_in_melee(attacker, is_counter=True)
            result_parts.append(f"[Counter] {defender.name}: {'; '.join(counter_log)}")
            
            if counter_hits > 0:
                cover_bonus = attacker.get_cover_bonus(self)
                wound_effect = attacker.take_hits(counter_hits, 0, cover_bonus)
                
                if wound_effect == WoundEffect.KNOCKED_OUT:
                    attacker.add_status_effect('UNCONSCIOUS')
                    self.units.remove(attacker)
                    result_parts.append(f"{attacker.name} destroyed before attacking!")
                    return " | ".join(result_parts)
                elif wound_effect == WoundEffect.SHAKEN:
                    attacker.add_status_effect('SHAKEN')
                    result_parts.append(f"{attacker.name} shaken!")
                    push_result = attacker.try_push(defender, self)
                    if push_result:
                        result_parts.append(f"{attacker.name} {push_result}")
        
        # Attacker's attack with Impact
        attack_hits, attack_log = attacker.fight_in_melee(defender, is_charging=True)
        result_parts.append(f"{attacker.name}: {'; '.join(attack_log)}")
        
        if attack_hits > 0:
            # Calculate AP from weapons and Lance
            total_ap = 0
            for weapon in attacker.weapons:
                if weapon.is_melee:
                    base_ap = weapon.special_rules.get("AP", 0)
                    lance_ap = 1 if "Lance" in weapon.special_rules else 0
                    total_ap = max(total_ap, base_ap + lance_ap)
            
            cover_bonus = defender.get_cover_bonus(self)
            wound_effect = defender.take_hits(attack_hits, total_ap, cover_bonus)
            
            if wound_effect == WoundEffect.KNOCKED_OUT:
                defender.add_status_effect('UNCONSCIOUS')
                self.units.remove(defender)
                result_parts.append(f"{defender.name} destroyed!")
                return " | ".join(result_parts)
            elif wound_effect == WoundEffect.SHAKEN:
                defender.add_status_effect('SHAKEN')
                result_parts.append(f"{defender.name} shaken!")
                push_result = defender.try_push(attacker, self)
                if push_result:
                    result_parts.append(f"{defender.name} {push_result}")
        
        # Defender strikes back (if still alive, not shaken, didn't counter)
        if (defender in self.units and not defender.shaken and 
            not defender.can_counter()):
            
            strike_back_hits, strike_back_log = defender.fight_in_melee(attacker)
            result_parts.append(f"{defender.name} strikes back: {'; '.join(strike_back_log)}")
            
            if strike_back_hits > 0:
                cover_bonus = attacker.get_cover_bonus(self)
                wound_effect = attacker.take_hits(strike_back_hits, 0, cover_bonus)
                
                if wound_effect == WoundEffect.KNOCKED_OUT:
                    attacker.add_status_effect('UNCONSCIOUS')
                    self.units.remove(attacker)
                    result_parts.append(f"{attacker.name} destroyed!")
                elif wound_effect == WoundEffect.SHAKEN:
                    attacker.add_status_effect('SHAKEN')
                    result_parts.append(f"{attacker.name} shaken!")
                    push_result = attacker.try_push(defender, self)
                    if push_result:
                        result_parts.append(f"{attacker.name} {push_result}")
        
        # Post-combat movement (simplified separation)
        if attacker in self.units and defender in self.units:
            # Try to move attacker back 1"
            new_pos = (max(0, attacker.position[0] - 1), attacker.position[1])
            if new_pos != defender.position:
                attacker.set_position(new_pos, attacker.elevation)
        
        return " | ".join(result_parts)
    
    def check_objective_control(self):
        """Enhanced objective control"""
        for objective in self.objectives:
            controlling_units = []
            
            for unit in self.units:
                if (not unit.shaken and not unit.deployed_via_ambush and
                    self.distance(unit.position, objective["position"]) <= 3):
                    controlling_units.append(unit)
            
            if not controlling_units:
                objective["controlled_by"] = None
                objective["contested"] = False
            elif len(set(u.player_id for u in controlling_units)) > 1:
                objective["controlled_by"] = None
                objective["contested"] = True
            else:
                objective["controlled_by"] = controlling_units[0]
                objective["contested"] = False
    
    def morale_phase(self):
        """Phase 3: Enhanced morale phase with Hero command"""
        player_units = {0: [], 1: []}
        heroes = {0: [], 1: []}
        
        for unit in self.units:
            player_units[unit.player_id].append(unit)
            if "Hero" in unit.special_rules and not unit.shaken:
                heroes[unit.player_id].append(unit)
        
        total_units = len(self.units)
        
        for player_id, units in player_units.items():
            if len(units) <= total_units / 4:  # Army broken
                # Find best hero quality for morale
                hero_quality = None
                for hero in heroes[player_id]:
                    for unit in units:
                        if self.distance(hero.position, unit.position) <= 12:
                            if hero_quality is None or hero.quality < hero_quality:
                                hero_quality = hero.quality
                
                for unit in units:
                    if not unit.morale_test(hero_quality):
                        if unit.shaken:
                            if unit in self.units:
                                unit.add_status_effect('UNCONSCIOUS')
                                self.units.remove(unit)
                        else:
                            unit.shaken = True
                            unit.add_status_effect('SHAKEN')
    
    def next_round(self):
        """Phase 3: Start new round with spell tokens"""
        self.round += 1
        
        # Update all unit effects
        self.update_unit_effects()
        
        # Reset activation and fatigue
        for unit in self.units:
            unit.activated = False
            unit.fatigued = False
            unit.deployed_via_ambush = False  # Can contest objectives again
            
            # Phase 3: Add spell tokens to casters
            if "Caster" in unit.special_rules:
                tokens_to_add = unit.special_rules["Caster"]
                added = unit.spell_tokens + tokens_to_add
                unit.spell_tokens = min(added, unit.max_spell_tokens)
                if tokens_to_add > 0:
                    print(f"{unit.name} gains {tokens_to_add} spell tokens ({unit.spell_tokens} total)")
        
        self.check_objective_control()
        self.morale_phase()
        
        self.current_player = 1 - self.current_player

    def ai_choose_unit(self, player_units):
        """Enhanced AI unit selection with Phase 3 priorities"""
        priority_units = []
        caster_units = []
        hero_units = []
        regular_units = []
        
        for unit in player_units:
            if not unit.activated:
                if "Hero" in unit.special_rules:
                    hero_units.append(unit)
                elif "Caster" in unit.special_rules and unit.spell_tokens > 0:
                    caster_units.append(unit)
                elif (unit.can_fly() or "Impact" in unit.special_rules or 
                      any("Blast" in w.special_rules or "Deadly" in w.special_rules for w in unit.weapons)):
                    priority_units.append(unit)
                else:
                    regular_units.append(unit)
        
        # Prioritize: Heroes > Casters with tokens > Special abilities > Regular
        for unit_list in [hero_units, caster_units, priority_units, regular_units]:
            if unit_list:
                return random.choice(unit_list)
        return None

    def ai_choose_action(self, unit, enemy_units):
        """Enhanced AI with Phase 3 tactics"""
        if not enemy_units:
            return Action.HOLD, None, None, 0

        # Phase 3: Try casting spells first
        if "Caster" in unit.special_rules and unit.spell_tokens > 0:
            # Find closest enemy for spell targeting
            closest_enemy = min(enemy_units, key=lambda e: unit.get_min_distance_to_target(e))
            distance = unit.get_min_distance_to_target(closest_enemy)
            
            # Try to cast offensive spells
            if unit.spell_tokens >= 3 and distance <= 18:  # Fireball range
                spell_success, spell_result = unit.cast_spell("Fireball", closest_enemy, self)
                if spell_success:
                    print(f"AI casts spell: {spell_result}")
            elif unit.spell_tokens >= 2 and distance <= 24:  # Lightning range
                spell_success, spell_result = unit.cast_spell("Lightning", closest_enemy, self)
                if spell_success:
                    print(f"AI casts spell: {spell_result}")

        # Find targets within range
        ranged_targets = []
        melee_targets = []
        blast_targets = []
        
        for enemy in enemy_units:
            distance = unit.get_min_distance_to_target(enemy)
            
            # Check for Blast weapons
            for weapon in unit.weapons:
                if "Blast" in weapon.special_rules and not weapon.is_melee and distance <= weapon.range:
                    blast_targets.append((enemy, distance))
                elif not weapon.is_melee and distance <= weapon.range:
                    ranged_targets.append((enemy, distance))
            
            # Check melee range
            if distance <= unit.move_types[Action.CHARGE]:
                melee_targets.append((enemy, distance))

        # Decision making with Phase 3 priorities
        # Blast weapons are high priority
        if blast_targets:
            target = min(blast_targets, key=lambda x: x[1])[0]
            return Action.HOLD, None, [target], 0
        
        # Flying units prefer to stay at range and shoot
        if unit.can_fly():
            if ranged_targets:
                target = min(ranged_targets, key=lambda x: x[1])[0]
                return Action.HOLD, None, [target], 0
            elif melee_targets:
                target = min(melee_targets, key=lambda x: x[1])[0]
                return Action.CHARGE, target.position, [target], target.elevation
        
        # Units with Impact or Deadly prefer to charge
        has_impact = any("Impact" in w.special_rules for w in unit.weapons if w.is_melee)
        has_deadly = any("Deadly" in w.special_rules for w in unit.weapons)
        
        if (has_impact or has_deadly) and melee_targets:
            target = min(melee_targets, key=lambda x: x[1])[0]
            return Action.CHARGE, target.position, [target], target.elevation
        
        # Ranged units prefer to shoot
        if ranged_targets:
            # Can target up to 2 enemies
            targets = [t[0] for t in sorted(ranged_targets, key=lambda x: x[1])[:2]]
            return Action.HOLD, None, targets, 0
        
        # Move toward closest enemy
        if enemy_units:
            closest = min(enemy_units, key=lambda e: unit.get_min_distance_to_target(e))
            return Action.ADVANCE, closest.position, None, closest.elevation
        
        return Action.HOLD, None, None, 0

def create_advanced_units():
    """Create units with Phase 3 special rules"""
    
    # Phase 3 weapons
    staff_of_power = Weapon("Staff of Power", 2, 12, special_rules={"Rending": True})
    war_cannon = Weapon("War Cannon", 1, 24, special_rules={"Blast": 3, "AP": 2})
    death_blade = Weapon("Death Blade", 2, 0, is_melee=True, special_rules={"Deadly": 2})
    hero_sword = Weapon("Hero Sword", 3, 0, is_melee=True, special_rules={"Impact": 1})
    
    # Phase 3 units
    archmage = Unit("Archmage", 3, 4, 80, 
                   {Action.HOLD: 0, Action.ADVANCE: 6, Action.RUSH: 12, Action.CHARGE: 12},
                   [staff_of_power], {"Caster": 3, "Hero": True, "Flying": True}, 2, 0)
    
    battle_lord = Unit("Battle Lord", 3, 3, 70,
                      {Action.HOLD: 0, Action.ADVANCE: 6, Action.RUSH: 12, Action.CHARGE: 12},
                      [hero_sword], {"Hero": True, "Fast": True}, 2, 1)
    
    war_cannons = Unit("War Cannons", 4, 4, 70,
                      {Action.HOLD: 0, Action.ADVANCE: 4, Action.RUSH: 8, Action.CHARGE: 8},
                      [war_cannon], {"Blast": 3, "Immobile": True, "AP": 2}, 1, 0, models=2)
    
    shadow_assassins = Unit("Shadow Assassins", 3, 4, 75,
                           {Action.HOLD: 0, Action.ADVANCE: 6, Action.RUSH: 12, Action.CHARGE: 12},
                           [death_blade], {"Deadly": 2, "Stealth": True}, 1, 1, models=3)
    
    return archmage, battle_lord, war_cannons, shadow_assassins

def main():
    # Initialize enhanced game
    game = Game(grid_size=20)
    
    # Create Phase 3 units
    archmage, battle_lord, war_cannons, shadow_assassins = create_advanced_units()
    
    # Add command groups
    war_cannons.has_musician = True
    shadow_assassins.has_sergeant = True
    
    # Deploy units
    game.add_unit(archmage, (4, 10))       # Hero caster
    game.add_unit(war_cannons, (6, 8))     # Blast weapons
    game.add_unit(battle_lord, (16, 12))   # Enemy hero
    game.add_unit(shadow_assassins, (14, 8)) # Deadly weapons
    
    # Add objectives
    game.add_objective((10, 5))
    game.add_objective((10, 15))
    game.add_objective((5, 10))
    game.add_objective((15, 10))
    game.add_objective((10, 10))
    
    print("\n" + "="*75)
    print(f"{Colors.BOLD}AGE OF FANTASY: SKIRMISH - PHASE 3 ADVANCED SYSTEMS{Colors.END}")
    print("="*75)
    print(f"{Colors.YELLOW}Phase 3 Features:{Colors.END}")
    print(f"• {Colors.GREEN}Blast(X) weapons{Colors.END} - multiply hits in area")
    print(f"• {Colors.PURPLE}Caster(X) units{Colors.END} - gain spell tokens each round")
    print(f"• {Colors.RED}Deadly(X) weapons{Colors.END} - multiply wounds on models")
    print(f"• {Colors.BLUE}Command Groups{Colors.END} - Sergeant/Musician/Banner bonuses")
    print(f"• {Colors.BOLD}Hero Command{Colors.END} - quality tests within 12\"")
    print(f"• {Colors.CYAN}Enhanced morale{Colors.END} and tactical depth")
    print(f"• {Colors.YELLOW}Dynamic visual effects{Colors.END} - See combat in real-time!")
    print("="*75)
    
    # Main game loop
    max_rounds = 4
    while (game.round <= max_rounds and 
           len([u for u in game.units if u.player_id == 0]) > 0 and 
           len([u for u in game.units if u.player_id == 1]) > 0):
        
        game.display_grid()
        
        player_units = [u for u in game.units if u.player_id == game.current_player and not u.activated]
        
        if not player_units:
            print(f"{game.players[game.current_player]} has no units left to activate.")
            time.sleep(1)
            game.next_round()
            continue
        
        # AI controls all units
        unit = game.ai_choose_unit(player_units)
        if not unit:
            game.next_round()
            continue
        
        enemy_units = [u for u in game.units if u.player_id != game.current_player]
        action, target_pos, target_units, target_elevation = game.ai_choose_action(unit, enemy_units)
        
        success, message = game.activate_unit(unit, action, target_pos, target_units, target_elevation)
        
        print(f"\n{Colors.BOLD}{game.players[game.current_player]} Action:{Colors.END} {message}")
        
        # Update effects after action
        game.update_unit_effects()
        
        time.sleep(2)  # Pause to show results
        
        # Check round completion
        player_units_left = [u for u in game.units if u.player_id == game.current_player and not u.activated]
        if not player_units_left:
            game.next_round()
    
    # Game over
    game.display_grid()
    game.check_objective_control()
    
    # Victory calculation
    player1_objs = len([o for o in game.objectives if o["controlled_by"] and o["controlled_by"].player_id == 0])
    player2_objs = len([o for o in game.objectives if o["controlled_by"] and o["controlled_by"].player_id == 1])
    player1_units = len([u for u in game.units if u.player_id == 0])
    player2_units = len([u for u in game.units if u.player_id == 1])
    
    print("\n" + "="*50)
    print(f"{Colors.BOLD}{Colors.GREEN}PHASE 3 ADVANCED COMBAT COMPLETE!{Colors.END}")
    print("="*50)
    
    if game.round > max_rounds:
        print("Game ended after 4 rounds")
    else:
        print("Game ended by elimination")
    
    print(f"{Colors.RED}Player 1:{Colors.END} {player1_units} units, {player1_objs} objectives")
    print(f"{Colors.BLUE}Player 2:{Colors.END} {player2_units} units, {player2_objs} objectives")
    
    if player1_objs > player2_objs:
        print(f"\n{Colors.RED}{Colors.BOLD}Player 1 wins by objectives!{Colors.END}")
    elif player2_objs > player1_objs:
        print(f"\n{Colors.BLUE}{Colors.BOLD}Player 2 wins by objectives!{Colors.END}")
    elif player1_units > player2_units:
        print(f"\n{Colors.RED}{Colors.BOLD}Player 1 wins by elimination!{Colors.END}")
    elif player2_units > player1_units:
        print(f"\n{Colors.BLUE}{Colors.BOLD}Player 2 wins by elimination!{Colors.END}")
    else:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}Complete draw!{Colors.END}")
    
    print(f"\n{Colors.BOLD}Phase 3 Features Demonstrated:{Colors.END}")
    print(f"✓ {Colors.PURPLE}Magic system{Colors.END} with Caster(X) and spell tokens")
    print(f"✓ {Colors.GREEN}Blast(X) area effect{Colors.END} weapons")
    print(f"✓ {Colors.RED}Deadly(X) wound multiplication{Colors.END}")
    print(f"✓ {Colors.BLUE}Command Groups{Colors.END} (Sergeant/Musician/Banner)")
    print(f"✓ {Colors.BOLD}Hero Command{Colors.END} and enhanced morale")
    print(f"✓ {Colors.CYAN}Advanced AI tactical{Colors.END} decision making")
    print(f"✓ {Colors.YELLOW}Dynamic visual effects{Colors.END} and status tracking")
    
    # Generate slideshow
    print(f"\n{Colors.CYAN}Generating slideshow...{Colors.END}")
    game.generate_slideshow()
    game.save_frames_as_text()

if __name__ == "__main__":
    main()