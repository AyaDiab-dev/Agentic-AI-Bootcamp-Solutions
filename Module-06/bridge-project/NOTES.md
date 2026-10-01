# Module 6 Bridge Project - Notes

## Results

The implementation passed all 17 checks in `verify_memory.py`. The memory game master scored 7/10 on night 2 and 8/10 on night 3, compared with the goldfish scores of 3/10 and 4/10. Each memory night performed two folds.

## A. My fold

I used a short-term token budget of `1200` tokens and kept the last `4` turns verbatim.

My fold prompt was:

```text
Rewrite the game memory as a concise factual summary of at most 120 words.

Preserve details needed to continue the adventure:
- the party's current location and destination;
- named characters and companions, including who is alive or dead;
- important items carried, lost, given away, or destroyed;
- promises, debts, goals, decisions, and unresolved dangers;
- important changes to the world.

Do not preserve decorative scenery, repeated dialogue, or casual chatter.
Do not invent facts.

EXISTING SUMMARY:
{self.summary or "(none)"}

OLDER TURNS TO FOLD:
{transcript or "(none)"}

Return only the updated summary.
```

For a retcon, I add an instruction to remove every mention of the requested subject.

I did not record a separate pre-tuning campaign run. The first complete implementation passed the fold checks and produced two folds per night. The first real quizzes still exposed details that were not recalled reliably. Night 2 missed the cart-wheel repair, Tobb's exact ledger promise, and two inventory items. Night 3 missed the rope bought from Mirra and the one-copper ferry price. I did not change the prompt after these runs because both quizzes met the required score and rerunning would replace the submitted evidence. A future revision should explicitly preserve prices, transaction dates, exact promised actions, and deadlines.

Observed maximum prompts:

| Run | Night 1 | Night 2 | Night 3 |
|---|---:|---:|---:|
| Memory GM | 2,164 | 2,325 | 2,332 |
| Goldfish | N/A | 2,877 | 2,647 |

The memory prompt reached a bounded plateau around 2.3k tokens, while the goldfish prompt was larger. Extraction makes one model call after every turn; this is the cost of using a model-written write policy.

## B. Marra and Mirra

Night 3 answers:

> **Is Marra the smith alive?**  
> No, Marra the smith is dead. She is buried behind the forge, a gentle reminder of her presence in the village.

> **Is Mirra the herbalist alive?**  
> Yes, Mirra the herbalist is alive and always busy in her shop.

The identity guard in `recall()` is:

```python
if metadata["type"] == "npc" and named_npcs:
    if not any(
        same_subject(metadata["subject"], named)
        for named in named_npcs
    ):
        continue
```

I did not remove this guard during the final campaign run, so I cannot claim a measured result without it. The automated verification did test the important outcome: a query naming Mirra never returned Marra. The guard is still necessary because vector similarity treats the similar names and their shared village context as semantically close. Retrieval correctness should not depend on the model noticing a one-letter difference after the wrong memory has already entered its context.

## C. The retcon

The night 3 receipt reported:

```text
5 rows deleted, 0 remaining
summary mentions it after re-fold: no
GM's next answer mentions it: no
```

The summary was the hardest place to make the subject disappear. Deleting ChromaDB rows removes long-term records, but the same information may still exist in the current night's rolling summary. Therefore `forget()` alone is insufficient; `fold(drop="amulet")` must rewrite the summary with an explicit exclusion rule.

The checks are correctly ordered:

1. Check the persistent store first, because it is the durable source.
2. Check the short-term summary next, because it may retain deleted information.
3. Check the next GM answer last, because it proves that neither memory path leaked the forgotten subject back into the response.

This produced a complete retcon across storage, context, and observable behavior.