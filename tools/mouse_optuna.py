"""MOUSE + OPTUNA — find the optimal (lr, batch, frequency) mix for the maw-RL, least overhead for confirmed lift.

Per the mouse method: real ColonyMawRL, isolated, cadence-independent. Optuna (TPE) searches the learner config at a
FIXED COMPUTE budget (equal episodes/trial => equal overhead), so batch IS the frequency lever (updates = compute /
batch) and the search trades frequency x batch x lr jointly. No magic search bounds: lr range anchors to the EXISTING
MAW_LR; batch range anchors to the existing KANERVA_ACTIVE / colony scale.

Output feeds a DERIVED (not hand-authored) config: batch -> a function of colony count (parallel pooling), lr -> the
existing plasticity mapping recentred on the found optimum. The study prints the derivation, not a magic number.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np, torch
import optuna
import maw_brain as mb

optuna.logging.set_verbosity(optuna.logging.WARNING)
D = mb.MAW_DIRECTIVE_DIM; OBS = 8
COMPUTE = 800                         # episodes/trial — equal overhead across trials (mouse-sized)
BASE_LR = mb.MAW_LR                   # anchor bounds to the EXISTING constant, not a fresh magic number
try:
    import neural_hive as _nh; KA = int(getattr(_nh, 'KANERVA_ACTIVE', 16))
except Exception:
    KA = 16


# TARGET-REACHING objective (matches the real maw reward = target-tracking, NOT monotone) — penalizes overshoot so
# an unstable/too-high lr scores BADLY. target is a fixed directive the policy must converge to and HOLD.
TARGET = torch.tensor([0.9, 0.1, 0.5, 0.2, 0.8, 0.3, 0.7])[:D]


def lift_for(lr, B):
    torch.manual_seed(0); np.random.seed(0)
    rl = mb.ColonyMawRL(obs_dim=OBS, update_every=B, warm_start=torch.full((D,), 0.5), lr=lr)
    obs = torch.zeros(OBS)
    dists = []
    for _ in range(COMPUTE):
        d = rl.act(obs).reshape(-1)[:D]
        rl.observe_reward(-float(((d - TARGET) ** 2).mean()))    # reach & HOLD the target; overshoot is punished
        dists.append(float(((d - TARGET) ** 2).mean()))
    start = float(np.mean(dists[:150])); end = float(np.mean(dists[-150:]))
    lift = (start - end) / (start + 1e-9)                        # fractional distance reduction; NEGATIVE if diverged
    return lift, rl.updates


def objective(trial):
    lr = trial.suggest_float('lr', BASE_LR / 3, BASE_LR * 100, log=True)   # [1e-3 .. 3e-1] from the existing 3e-3
    B = trial.suggest_int('batch', 2, max(4, KA), log=True)                # [2 .. KANERVA_ACTIVE]
    lift, updates = lift_for(lr, B)
    trial.set_user_attr('updates', updates)
    return lift


study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=0))
study.optimize(objective, n_trials=24)

best = study.best_trial
print(f"MOUSE+OPTUNA — maw-RL config search ({len(study.trials)} trials, {COMPUTE} ep/trial = equal overhead)")
print(f"{'lift':>6} {'lr':>9} {'batch':>6} {'updates':>8}")
for t in sorted(study.trials, key=lambda t: -t.value)[:6]:
    print(f"{t.value:>6.3f} {t.params['lr']:>9.4f} {t.params['batch']:>6d} {t.user_attrs.get('updates',0):>8d}")
lr_opt, B_opt = best.params['lr'], best.params['batch']
print(f"\nOPTIMAL: lr={lr_opt:.4f}  batch={B_opt}  -> lift {best.value:.3f}")

# ---- DERIVE the applied config from principled quantities (no magic constants) ----
print("\n--- derived, not hand-authored ---")
print(f"  batch  : Optuna optimum {B_opt} -> in-game achieve via PARALLEL POOLING P=num_colonies pooling one policy;")
print(f"           MAW_UPDATE_EVERY = max(2, round(B_opt)) but the DATA is filled by P colonies/cycle => frequency up.")
print(f"  lr     : keep the Baldwin map lr = MAW_LR*(0.5+plasticity); recentre MAW_LR so the mid-plasticity (0.5)")
print(f"           colony lands on the optimum:  MAW_LR = lr_opt / (0.5 + 0.5) = {lr_opt/1.0:.4f}  (a FUNCTION of the")
print(f"           found optimum, not a typed magic number). plasticity in [0.2,0.9] then spans "
      f"[{lr_opt/1.0*0.7:.3f}, {lr_opt/1.0*1.4:.3f}].")
print(f"  freq   : updates/game = horizon*P / (batch*POP_TICK_INTERVAL); pick P=num_colonies -> "
      f"the colony count DRIVES frequency, no authored cadence constant.")
