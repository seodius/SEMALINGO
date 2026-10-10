# Exit questions

SEMALINGO is built to answer concrete questions first; new questions go into a question
log and are ranked in only after question 1 is answered. The first use case is the design
of a constructed language: choosing its lexemes and affixes from evidence.

## Ranked

| Rank | Question | Kind | Needs beyond the first wave |
| --- | --- | --- | --- |
| 1 | Q1 + Q2: which lexeme candidates are learnable at 12, stable across languages and collapsible into words, and which affixes maximize those collapses? Report coverage for the top N. | Build | Nothing |
| 2 | Q4: where do ontology distances (SUMO/WordNet) disagree with word associations and colexification? | Research | Small World of Words |
| 3 | Q3a: are the words for the semantic primes among the earliest words children learn, across languages? | Research | Wordbank |
| 4 | Q5: how far do a concept's centre points drift across languages, and how do LLM concept spaces differ from human ones? | Research | Computed embeddings |
| 5 | Q3b: do the primes anchor vocabulary in second-language learning? | Research, parked | Learner vocabulary data by level |

## Question 1, defined

Find the lexemes and affixes such that:

1. they fit the budget: about 650 lexemes and about 100 affix slots;
2. they form as many collapses (lexeme + affix) into words as possible;
3. every collapse is unambiguous: one target word, whatever the context;
4. every affix moves every lexeme in the same direction; further precision comes from modifier words;
5. they are learnable and intuitive for 12-year-olds and second-language learners;
6. collapses teach true relations (a peanut collapses as a legume, not a nut);
7. they are stable across languages.

| Criterion | Proposed measure | Still open |
| --- | --- | --- |
| Budget | lexemes and affix slots used | nothing |
| Collapses | share of a target vocabulary reached through lexeme + affix collapses | which target vocabulary |
| Unambiguous | how many target words a collapse could mean, including the spread of free answers in the analogy test | threshold |
| Consistent | how uniform each affix's effect is across lexemes: the same analogy test, run over many lexemes per affix | measured on typed graph edges or on embeddings |
| Learnable at 12 | test-based AoA (English, per meaning), rated AoA (English, Dutch), presence in children's texts | thresholds |
| Intuitive | analogy test (SOUND+SENSE = HEAR, so LIGHT+SENSE = ?): small LLMs first, then classrooms of 12-year-olds; share of free answers that hit the intended word | test design; consent and ethics review for classroom work |
| Second-language learners | no source yet | a source or a proxy |
| Teaches true relations | agreement with the ontology where folk associations disagree; Q4 finds those cases | its weight against intuitive |
| Stable across languages | early learning across Wordbank languages, semantic shifts, colexification profile | whether colexification counts for or against; concrete and abstract judged separately or together |

**Weights, not filters.** The criteria trade off against each other, so the tool returns
the trade-off front (the Pareto front) instead of one answer. A released design is one
chosen point on that front, and its weights are published with it, so others can rerun
the optimization with their own priorities.
