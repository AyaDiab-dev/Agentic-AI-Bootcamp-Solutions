# Vendor Onboarding Desk — Notes

## A. Where did the budget force a real trade-off?

I chose not to spend a GLEIF or web lookup on Al Wasel and Babel General
Trading LLC after its sanctions evidence crossed the selected threshold.
The OFAC result was already sufficient to reject the payment, so an additional
identity lookup would not have changed the decision.

This preserved the limited budget for ambiguous suppliers such as Almarai
Company and Zorblax Trading FZE, where GLEIF returned no records and a web
search was needed to distinguish a real company from an entity with no
verifiable trace. The final run used eight of the nine available lookups and
still produced a verdict for all seven suppliers.

## B. What sanctions threshold did you set, and why?

I selected a sanctions similarity threshold of 0.90. The project evidence
showed that legitimate suppliers could receive noisy similarity scores between
approximately 0.71 and 0.81 because of common words such as "Trading" or
"Company." The genuinely listed supplier produced a score of 1.00.

A threshold that was too low could create a false positive and unnecessarily
block payment to an honest supplier. A threshold that was too high could create
a false negative and allow payment to a sanctioned entity, which could have
serious legal and financial consequences. For that reason, scores below 0.90
are treated as possible fuzzy-match noise, while a score at or above 0.90
triggers rejection and referral to Legal.

## C. Where did the agent nearly get it wrong?

In the first run, the agent saw the 1.00 OFAC match for Al Wasel and Babel
General Trading LLC but returned CONDITIONS instead of REJECT. The prompt
already instructed the model to reject a strong sanctions match, but the model
did not follow that instruction reliably.

I fixed this by enforcing the sanctions threshold in Python code before asking
the model for a general verdict. When the score reaches the threshold, the code
directly creates a REJECT verdict and stops further identity lookups for that
supplier. This demonstrated an important lesson: prompts request behavior, but
code must enforce rules that cannot safely be ignored.

I also refined the LAPSED check so that ACTIVE, LAPSED, and an exact name match
must appear in the same GLEIF candidate. Without that change, status fields
from different candidates could be combined incorrectly.

## Repeatability

I ran the agent more than once. The wording of the planning reasons and final
explanations changed slightly because LLM output is non-deterministic, but the
final verdicts remained consistent across the final runs.