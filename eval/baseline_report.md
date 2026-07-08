# TruthLayer eval report — baseline

Run: `20260708T182007Z` · 40 scored / 40 total (0 errored)

## Headline numbers

- **Verdict accuracy: 77.5%**
- Retrieval hit rate (reference domain cited): 42.9% over 35 claims
- Latency: p50 14.9s · p95 25.1s
- Avg LLM calls per claim: 2.02
- Avg tokens per claim: 3426 in / 230 out → **cost per verdict ≈ $0.0092**


## Per-stage latency (avg seconds per claim)

| stage | avg s |
|---|---|
| broaden | 1.74 |
| decompose | 1.80 |
| finalize | 0.00 |
| judge | 3.04 |
| retrieve | 0.09 |
| search_and_embed | 10.95 |

## Confusion matrix (rows = expected, columns = predicted)

| expected \ predicted | true | false | mixed | unverifiable |
|---|---|---|---|---|
| **true** | 13 | 0 | 0 | 0 |
| **false** | 0 | 13 | 0 | 0 |
| **mixed** | 0 | 5 | 2 | 0 |
| **unverifiable** | 0 | 4 | 0 | 3 |

## Accuracy by difficulty

- easy: 100.0%
- hard: 16.7%
- medium: 63.6%

## Failures

### #27: Tesla was founded by Elon Musk in 2003.
- expected **mixed**, predicted **false** (confidence 0.95)
- rationale: Evidence shows Tesla was founded in 2003 by Martin Eberhard and Marc Tarpenning, not Elon Musk. Musk joined later as an investor and board chair in 2004 and became CEO in 2008, though he is legally recognized as one of five co-founders.
- sources: https://www.investopedia.com/articles/personal-finance/061915/story-behind-teslas-success.asp, https://www.facebook.com/FortuneMagazine/posts/-today-marks-23-years-since-tesla-was-founded-on-july-1-2003-since-then-it-has-b/1373947571262320

### #28: Christopher Columbus reached the Americas in 1492, proving for the first time that the Earth was round.
- expected **mixed**, predicted **false** (confidence 0.95)
- rationale: The evidence consistently shows that educated Europeans, including Columbus, already knew the Earth was round before 1492. His voyage did not prove the Earth was round; this is a well-documented myth traced to Washington Irving's 1828 book.
- sources: https://www.csmonitor.com/USA/2011/1010/Christopher-Columbus-Five-things-you-thought-you-knew-about-the-explorer/MYTH-Columbus-set-out-to-prove-the-earth-was-round, https://www.history.com/articles/christopher-columbus-never-set-out-to-prove-the-earth-was-round, https://pwg.gsfc.nasa.gov/stargaze/Scolumb.htm, https://www.ripleys.com/stories/columbus-earth, https://www.youtube.com/watch?v=F_Tbw5q219w

### #29: The Berlin Wall fell in 1989, marking the official end of World War II.
- expected **mixed**, predicted **false** (confidence 0.97)
- rationale: The Berlin Wall did fall in 1989, marking the end of the Cold War, but World War II officially ended in 1945 with VE Day, as evidence explicitly states. The claim conflates two distinct historical events.
- sources: https://www.hiddenmonuments.com/blog/80-years-end-of-world-war-II, https://en.wikipedia.org/wiki/Fall_of_the_Berlin_Wall

### #31: Albert Einstein won the 1921 Nobel Prize in Physics for his theory of relativity.
- expected **mixed**, predicted **false** (confidence 0.97)
- rationale: The evidence clearly states Einstein received the 1921 Nobel Prize in Physics for his discovery of the law of the photoelectric effect, not for relativity, which was explicitly excluded from the official citation.
- sources: https://www.advancedsciencenews.com/the-dramatic-story-behind-general-relativitys-nobel-prize-snub, https://www.theatlantic.com/technology/archive/2014/09/einstein-didnt-win-a-nobel-for-relativity-he-won-it-for-this/380451

### #33: The Titanic sank in 1912 on its maiden voyage after hitting an iceberg, killing everyone on board.
- expected **mixed**, predicted **false** (confidence 0.97)
- rationale: Evidence confirms Titanic sank in 1912 on its maiden voyage after hitting an iceberg, but contradicts the claim that everyone died—about 1,500 died while roughly 710 survived.
- sources: https://www.britannica.com/event/How-many-people-died-when-the-Titanic-sank, https://www.facebook.com/ABCNews/posts/on-this-day-in-1912-the-british-luxury-liner-rms-titanic-sunk-in-the-north-atlan/1379944633992413

### #34: There are exactly 3 trillion fish in the Pacific Ocean right now.
- expected **unverifiable**, predicted **false** (confidence 0.75)
- rationale: Evidence gives an estimate of about 3.5 trillion fish in the whole ocean (not specifically the Pacific), an approximation not an exact real-time count, and no source confirms 'exactly 3 trillion in the Pacific right now'.
- sources: https://about.conservationevidence.com/2022/07/11/plenty-more-fish-in-the-ce-synopsis-on-marine-fish-conservation

### #35: Extraterrestrials visited Earth during the construction of the Egyptian pyramids.
- expected **unverifiable**, predicted **false** (confidence 0.85)
- rationale: The evidence consists of Quora discussions explicitly stating there is no evidence extraterrestrials helped build the pyramids, and that human labor and technique fully explain the construction. No credible evidence supports extraterrestrial involvement.
- sources: https://www.quora.com/Is-there-any-evidence-to-support-the-theory-of-aliens-visiting-Earth-in-ancient-times-such-as-during-the-construction-of-the-Egyptian-pyramids-What-is-your-opinion-on-this-topic-and-why

### #37: A butterfly flapping its wings in Brazil caused Hurricane Katrina.
- expected **unverifiable**, predicted **false** (confidence 0.95)
- rationale: The butterfly effect is a metaphor from chaos theory illustrating sensitivity to initial conditions, not a literal causal claim. Evidence explicitly states the butterfly does not power or directly create the tornado, and the concept has never been rigorously verified as literal causation. There is no evidence linking any butterfly to Hurricane Katrina specifically.
- sources: https://en.wikipedia.org/wiki/Butterfly_effect, https://www.americanscientist.org/article/understanding-the-butterfly-effect

### #38: Shakespeare's plays were secretly written by Francis Bacon.
- expected **unverifiable**, predicted **false** (confidence 0.9)
- rationale: The evidence describes the Baconian theory as a fringe hypothesis, explicitly stating that 'all but a few academic Shakespeare scholars reject the arguments for Bacon authorship.' This indicates the claim is not supported by mainstream scholarship and is considered a discredited or minority theory rather than an established fact.
- sources: https://en.wikipedia.org/wiki/Baconian_theory_of_Shakespeare_authorship
