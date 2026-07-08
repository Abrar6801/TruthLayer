# TruthLayer eval report — rerank_parallel

Run: `20260708T183028Z` · 40 scored / 40 total (0 errored)

## Headline numbers

- **Verdict accuracy: 75.0%**
- Retrieval hit rate (reference domain cited): 40.0% over 35 claims
- Latency: p50 10.5s · p95 15.3s
- Avg LLM calls per claim: 2.00
- Avg tokens per claim: 3379 in / 223 out → **cost per verdict ≈ $0.0090**


## Per-stage latency (avg seconds per claim)

| stage | avg s |
|---|---|
| decompose | 2.17 |
| finalize | 0.00 |
| judge | 3.48 |
| retrieve | 1.24 |
| search_and_embed | 4.73 |

## Confusion matrix (rows = expected, columns = predicted)

| expected \ predicted | true | false | mixed | unverifiable |
|---|---|---|---|---|
| **true** | 13 | 0 | 0 | 0 |
| **false** | 0 | 13 | 0 | 0 |
| **mixed** | 0 | 6 | 1 | 0 |
| **unverifiable** | 0 | 4 | 0 | 3 |

## Accuracy by difficulty

- easy: 100.0%
- hard: 16.7%
- medium: 54.5%

## Failures

### #27: Tesla was founded by Elon Musk in 2003.
- expected **mixed**, predicted **false** (confidence 0.95)
- rationale: Evidence consistently shows Tesla was founded in July 2003 by Martin Eberhard and Marc Tarpenning, not Elon Musk, who joined later as an early investor and board member before becoming CEO in 2008. While Tesla later legally recognized Musk as one of five founders, the claim that he founded the company in 2003 is contradicted by multiple sources.
- sources: https://www.investopedia.com/articles/personal-finance/061915/story-behind-teslas-success.asp, https://en.wikipedia.org/wiki/History_of_Tesla,_Inc., https://www.facebook.com/FortuneMagazine/posts/-today-marks-23-years-since-tesla-was-founded-on-july-1-2003-since-then-it-has-b/1373947571262320

### #28: Christopher Columbus reached the Americas in 1492, proving for the first time that the Earth was round.
- expected **mixed**, predicted **false** (confidence 0.97)
- rationale: The evidence consistently shows that educated people, including Columbus and his contemporaries, already knew the Earth was round before 1492. The idea that Columbus 'proved' the Earth was round is a well-documented myth originating from Washington Irving's 1828 biography, not historical fact.
- sources: https://www.history.com/articles/christopher-columbus-never-set-out-to-prove-the-earth-was-round, https://www.csmonitor.com/USA/2011/1010/Christopher-Columbus-Five-things-you-thought-you-knew-about-the-explorer/MYTH-Columbus-set-out-to-prove-the-earth-was-round, https://pwg.gsfc.nasa.gov/stargaze/Scolumb.htm, https://www.youtube.com/watch?v=F_Tbw5q219w

### #29: The Berlin Wall fell in 1989, marking the official end of World War II.
- expected **mixed**, predicted **false** (confidence 0.97)
- rationale: The Berlin Wall did fall in 1989, but the evidence shows it marked the end of the Cold War, not World War II, which ended in 1945. World War II had already ended decades before the wall fell.
- sources: https://www.nationalww2museum.org/war/articles/all-fall-down-end-world-war-ii-europe, https://www.ebsco.com/research-starters/history/fall-berlin-wall, https://en.wikipedia.org/wiki/Fall_of_the_Berlin_Wall

### #30: Mount Everest, located in Japan, is the tallest mountain above sea level.
- expected **mixed**, predicted **false** (confidence 0.95)
- rationale: Mount Everest is located in Nepal/Tibet (China), not Japan; the evidence discusses Japanese expeditions climbing Everest, not Everest being located in Japan. The claim's location is factually incorrect based on context.
- sources: https://www.himalayanclub.org/hj/31/8/the-japanese-mount-everest-expedition-1969-1970

### #31: Albert Einstein won the 1921 Nobel Prize in Physics for his theory of relativity.
- expected **mixed**, predicted **false** (confidence 0.97)
- rationale: Evidence clearly states Einstein received the 1921 Nobel Prize in Physics for his discovery of the law of the photoelectric effect, not for the theory of relativity.
- sources: https://www.theatlantic.com/technology/archive/2014/09/einstein-didnt-win-a-nobel-for-relativity-he-won-it-for-this/380451, https://www.advancedsciencenews.com/the-dramatic-story-behind-general-relativitys-nobel-prize-snub

### #33: The Titanic sank in 1912 on its maiden voyage after hitting an iceberg, killing everyone on board.
- expected **mixed**, predicted **false** (confidence 0.97)
- rationale: Evidence confirms the Titanic sank in 1912 on its maiden voyage after hitting an iceberg, but 710 survived per ABC News and 705 per Britannica, contradicting the claim that everyone died.
- sources: https://www.facebook.com/ABCNews/posts/on-this-day-in-1912-the-british-luxury-liner-rms-titanic-sunk-in-the-north-atlan/1379944633992413, https://www.britannica.com/topic/Titanic

### #34: There are exactly 3 trillion fish in the Pacific Ocean right now.
- expected **unverifiable**, predicted **false** (confidence 0.75)
- rationale: The evidence estimates about 3.5 trillion fish in all oceans combined (not specifically the Pacific), and it is explicitly stated this is an estimate that is 'ever changing' and impossible to count precisely. The claim's specific figure of 'exactly 3 trillion' for the Pacific Ocean alone is not supported and contradicts the cited estimate.
- sources: https://about.conservationevidence.com/2022/07/11/plenty-more-fish-in-the-ce-synopsis-on-marine-fish-conservation

### #35: Extraterrestrials visited Earth during the construction of the Egyptian pyramids.
- expected **unverifiable**, predicted **false** (confidence 0.85)
- rationale: The evidence explicitly states there is no evidence that extraterrestrials helped build the pyramids, and explains the pyramids could be built with human labor and hard work without advanced technology.
- sources: https://www.quora.com/Is-there-any-evidence-to-support-the-theory-of-aliens-visiting-Earth-in-ancient-times-such-as-during-the-construction-of-the-Egyptian-pyramids-What-is-your-opinion-on-this-topic-and-why

### #37: A butterfly flapping its wings in Brazil caused Hurricane Katrina.
- expected **unverifiable**, predicted **false** (confidence 0.9)
- rationale: The butterfly effect is a metaphorical/theoretical concept illustrating sensitivity to initial conditions in chaotic systems, not a literal, verifiable causal claim about a specific real hurricane. Evidence shows the concept originated as a hypothetical question and was never intended to imply actual causation, and there is no evidence linking a butterfly to Hurricane Katrina specifically.
- sources: https://en.wikipedia.org/wiki/Butterfly_effect, https://www.americanscientist.org/article/understanding-the-butterfly-effect

### #38: Shakespeare's plays were secretly written by Francis Bacon.
- expected **unverifiable**, predicted **false** (confidence 0.9)
- rationale: The evidence describes the Baconian theory as a fringe hypothesis, explicitly stating that nearly all academic Shakespeare scholars reject the claim that Francis Bacon wrote Shakespeare's plays. Thus the claim is not supported as fact but is a rejected conspiracy theory.
- sources: https://en.wikipedia.org/wiki/Baconian_theory_of_Shakespeare_authorship
