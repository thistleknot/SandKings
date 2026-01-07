from corewar_util import SimulationArgs, parse_warrior_from_file, run_multiple_rounds, simargs_to_environment
from llm_corewar import CorewarGPT
import asyncio

simargs = SimulationArgs()

system_prompt = "./prompts/system_prompt_0.txt"
new_warrior_prompt = "./prompts/new_prompt_0.txt"
mutate_warrior_prompt = "./prompts/mutate_prompt_0.txt"

with open(system_prompt, "r") as f:
    system_prompt = f.read()
with open(new_warrior_prompt, "r") as f:
    new_warrior_prompt = f.read()
with open(mutate_warrior_prompt, "r") as f:
    mutate_warrior_prompt = f.read()

gpt = CorewarGPT("gpt-4.1-mini-2025-04-14", system_prompt, new_warrior_prompt, mutate_warrior_prompt, temperature=1., environment=simargs_to_environment(simargs))

new_warriors = asyncio.run(gpt.new_warrior_async(n_warriors=1, n_responses=8)).flatten() # get 8 new warriors
new_warriors = [w for w in new_warriors if w is not None and w.warrior is not None]
for w in new_warriors:
    print('--------------------------------')
    print(w.warrior)
    print(w.llm_response)
    print(w.warrior)
    for i in w.warrior.instructions:
        print(i)

w = new_warriors[0]
mutated_warriors = asyncio.run(gpt.mutate_warrior_async([w], n_responses=4)).flatten() # get 4 mutations of warrior w
mutated_warriors = [w for w in mutated_warriors if w is not None and w.warrior is not None]

for w in mutated_warriors:
    print('--------------------------------')
    print(w.warrior)
    print(w.llm_response)
    for i in w.warrior.instructions:
        print(i)