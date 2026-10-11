# Golden questions

Questions with known answers that must still pass after every rebuild of the graph
(step 6). Each one names the operation, its input and the expected result, for example:
"`colexifications(concepticon:<ARM>)` includes HAND". They are added as soon as the first
loaders and operations exist, starting with the cases behind the exit questions.

The questions are in [questions.yaml](questions.yaml); `semalingo golden` asks them, and the
Load sources workflow asks them on every rebuild.
