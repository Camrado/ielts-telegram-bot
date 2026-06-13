"""
Idempotent seed script for shared grammar content (user_id = NULL).
Run: python -m bot.seed_grammar
"""

import asyncio
import json
import logging

from bot.database import create_pool, close_pool, get_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# TOPIC 1: Articles
# ═══════════════════════════════════════════════════════════════════════════

ARTICLES_TOPIC = {
    "name": "Articles — a, an, the, zero article",
    "description": "Mastering the use of a, an, the, and zero article in academic writing",
}

ARTICLES_RULES = [
    {
        "rule_title": '"a" vs "an" — based on sound, not letter',
        "rule_text": (
            'Use "a" before consonant SOUNDS and "an" before vowel SOUNDS. '
            "The choice depends on pronunciation, not spelling. "
            '"An hour" (silent h), "a university" (starts with /juː/), '
            '"an MBA" (starts with /ɛm/).'
        ),
        "correct_example": "An honest approach to education reform is needed.",
        "incorrect_example": "A honest approach to education reform is needed.",
        "tip": 'Say the next word aloud — if it starts with a vowel sound, use "an".',
        "sort_order": 1,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct sentence:",
                "correct_answer": "She earned an MBA from a European university.",
                "wrong_answers": [
                    "She earned a MBA from an European university.",
                    "She earned a MBA from a European university.",
                    "She earned an MBA from an European university.",
                ],
                "explanation": '"MBA" starts with vowel sound /ɛm/ → "an MBA". "European" starts with /jʊ/ (consonant sound) → "a European".',
            },
            {
                "question_type": "fill_blank",
                "prompt": "It took ___ hour to complete the examination.",
                "correct_answer": "an",
                "wrong_answers": ["a", "the", "—"],
                "explanation": '"Hour" has a silent h, so it starts with the vowel sound /aʊ/ → "an hour".',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "A uniform policy was introduced across all universities.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"Uniform" begins with /juː/ (consonant sound), so "a" is correct.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "The researcher proposed ___ unique solution to the problem.",
                "correct_answer": "a",
                "wrong_answers": ["an", "the", "—"],
                "explanation": '"Unique" starts with the consonant sound /juː/, so "a" is correct.',
            },
        ],
    },
    {
        "rule_title": "First mention (a/an) vs subsequent mention (the)",
        "rule_text": (
            "Use a/an when introducing something for the first time. "
            'Use "the" when referring back to it, because the reader now knows '
            "which specific item you mean."
        ),
        "correct_example": "A study was conducted in 2020. The study found that screen time affects sleep quality.",
        "incorrect_example": "The study was conducted in 2020. A study found that screen time affects sleep quality.",
        "tip": "First time → a/an (new info). After that → the (now known).",
        "sort_order": 2,
        "questions": [
            {
                "question_type": "fill_blank",
                "prompt": "___ survey was distributed to 500 participants. ___ survey revealed significant differences in opinion.",
                "correct_answer": "A, The",
                "wrong_answers": ["The, The", "A, A", "The, A"],
                "explanation": "First mention uses 'a' (new information). Second mention uses 'the' (the reader now knows which survey).",
            },
            {
                "question_type": "pick_correct",
                "prompt": "Which pair correctly uses articles for first and second mention?",
                "correct_answer": "A new policy was proposed. The policy aimed to reduce emissions.",
                "wrong_answers": [
                    "The new policy was proposed. A policy aimed to reduce emissions.",
                    "The new policy was proposed. The policy aimed to reduce emissions.",
                    "A new policy was proposed. A policy aimed to reduce emissions.",
                ],
                "explanation": "The first sentence introduces the policy (a new policy). The second refers back to it (the policy).",
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "A report was published last year. A report highlighted the importance of early intervention.",
                "correct_answer": "Incorrect",
                "wrong_answers": [],
                "explanation": 'The second sentence refers to the same report, so it should use "the": "The report highlighted...".',
            },
        ],
    },
    {
        "rule_title": '"the" with superlatives and ordinals',
        "rule_text": (
            'Always use "the" before superlative adjectives (the most, the best, the largest) '
            "and ordinal numbers (the first, the second, the third). These identify a unique or "
            "specific item in a group."
        ),
        "correct_example": "Finland has the best education system in the world.",
        "incorrect_example": "Finland has best education system in world.",
        "tip": "Superlative = unique = the. First/second/third = unique position = the.",
        "sort_order": 3,
        "questions": [
            {
                "question_type": "fill_blank",
                "prompt": "China is ___ most populous country in ___ world.",
                "correct_answer": "the, the",
                "wrong_answers": ["a, the", "the, a", "—, —"],
                "explanation": 'Superlative "most populous" requires "the". "The world" is a unique noun.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The first step in addressing climate change is reducing carbon emissions.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": 'Ordinals always take "the" — "the first step" is correct.',
            },
            {
                "question_type": "error_correction",
                "prompt": "This is most significant challenge that governments face today.",
                "correct_answer": "This is the most significant challenge that governments face today.",
                "wrong_answers": [],
                "explanation": 'Superlatives require "the" — "the most significant".',
            },
        ],
    },
    {
        "rule_title": '"the" with unique nouns',
        "rule_text": (
            'Use "the" with nouns that are one of a kind or contextually unique: '
            "the sun, the moon, the internet, the government, the economy, the environment, "
            "the media, the public. The listener/reader knows exactly which one is meant."
        ),
        "correct_example": "The government should invest more in the environment.",
        "incorrect_example": "Government should invest more in environment.",
        "tip": 'If there is only one of it (or one obvious one in context), use "the".',
        "sort_order": 4,
        "questions": [
            {
                "question_type": "fill_blank",
                "prompt": "___ internet has transformed ___ way people communicate.",
                "correct_answer": "The, the",
                "wrong_answers": ["An, the", "The, a", "—, —"],
                "explanation": '"The internet" is a unique noun. "The way" refers to a specific way.',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct sentence:",
                "correct_answer": "The media plays a significant role in shaping public opinion.",
                "wrong_answers": [
                    "Media plays a significant role in shaping the public opinion.",
                    "A media plays a significant role in shaping public opinion.",
                    "Media plays significant role in shaping public opinion.",
                ],
                "explanation": '"The media" is a unique collective noun and requires "the". "Public opinion" is an uncountable abstract concept used in a general sense.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Economy of this country depends heavily on tourism.",
                "correct_answer": "Incorrect",
                "wrong_answers": [],
                "explanation": '"Economy" here refers to a specific one (this country\'s), so it needs "the": "The economy of this country...".',
            },
        ],
    },
    {
        "rule_title": "Zero article with uncountable abstract nouns (general sense)",
        "rule_text": (
            "When talking about uncountable abstract nouns in a GENERAL sense, "
            "use NO article (zero article). This includes: education, technology, "
            "health, information, research, crime, poverty, unemployment, globalisation, "
            "pollution, progress, knowledge, evidence. "
            'Adding "the" makes it specific.'
        ),
        "correct_example": "Education is the key to economic development.",
        "incorrect_example": "The education is the key to economic development.",
        "tip": 'General concept → no article. Specific instance → "the". Ask: "Am I talking about ALL of it in general, or a specific one?"',
        "sort_order": 5,
        "questions": [
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The technology has changed the way we live.",
                "correct_answer": "Incorrect",
                "wrong_answers": [],
                "explanation": '"Technology" in a general sense takes no article: "Technology has changed the way we live."',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence correctly uses the zero article?",
                "correct_answer": "Unemployment is a major social issue in many developing countries.",
                "wrong_answers": [
                    "The unemployment is a major social issue in many developing countries.",
                    "An unemployment is a major social issue in many developing countries.",
                    "The unemployment is the major social issue in many developing countries.",
                ],
                "explanation": '"Unemployment" is an uncountable abstract noun used in a general sense — no article needed.',
            },
            {
                "question_type": "error_correction",
                "prompt": "The poverty remains a serious problem in many parts of the world.",
                "correct_answer": "Poverty remains a serious problem in many parts of the world.",
                "wrong_answers": [],
                "explanation": '"Poverty" in a general sense does not take an article.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "___ research suggests that ___ exercise improves mental health.",
                "correct_answer": "—, —",
                "wrong_answers": ["The, the", "A, an", "The, —"],
                "explanation": 'Both "research" and "exercise" are used as general concepts here — no article needed for either.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Crime is increasing in urban areas due to inequality.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"Crime" and "inequality" are abstract nouns used generally — zero article is correct.',
            },
        ],
    },
    {
        "rule_title": "Zero article with plural countable nouns (general sense)",
        "rule_text": (
            "When making general statements about a whole category of people or things, "
            "use plural countable nouns with NO article. "
            '"Children need guidance" (all children in general). '
            '"The children need guidance" (specific children).'
        ),
        "correct_example": "Students who study abroad develop greater independence.",
        "incorrect_example": "The students who study abroad develop greater independence.",
        "tip": "If you mean ALL members of a group in general, drop the article entirely.",
        "sort_order": 6,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence is correct when making a general statement?",
                "correct_answer": "Teachers play a vital role in shaping future generations.",
                "wrong_answers": [
                    "The teachers play a vital role in shaping future generations.",
                    "A teachers play a vital role in shaping future generations.",
                    "The teachers play the vital role in shaping the future generations.",
                ],
                "explanation": 'General statement about all teachers → no article. "The teachers" would mean specific ones.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The governments should prioritise healthcare and education.",
                "correct_answer": "Incorrect",
                "wrong_answers": [],
                "explanation": 'If meaning governments in general, no article is needed: "Governments should prioritise...".',
            },
            {
                "question_type": "error_correction",
                "prompt": "The smartphones have become an essential part of daily life.",
                "correct_answer": "Smartphones have become an essential part of daily life.",
                "wrong_answers": [],
                "explanation": 'General statement about all smartphones → zero article.',
            },
        ],
    },
    {
        "rule_title": '"the" with specific/defined instances',
        "rule_text": (
            'Use "the" when the noun is made specific by a defining phrase, '
            "usually with a prepositional phrase (of, in, at) or a relative clause. "
            "Compare: 'Education is important' (general) vs "
            "'The education system in Finland is highly regarded' (specific)."
        ),
        "correct_example": "The unemployment rate in Spain has decreased significantly.",
        "incorrect_example": "Unemployment rate in Spain has decreased significantly.",
        "tip": 'If a phrase after the noun narrows it to a specific one, add "the".',
        "sort_order": 7,
        "questions": [
            {
                "question_type": "fill_blank",
                "prompt": "___ quality of education in rural areas is often lower than in cities.",
                "correct_answer": "The",
                "wrong_answers": ["A", "—", "An"],
                "explanation": '"Quality of education in rural areas" is made specific by the prepositional phrases → "the" is required.',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct sentence:",
                "correct_answer": "The impact of social media on teenagers has been widely studied.",
                "wrong_answers": [
                    "Impact of social media on teenagers has been widely studied.",
                    "An impact of social media on teenagers has been widely studied.",
                    "A impact of social media on teenagers has been widely studied.",
                ],
                "explanation": '"Impact" is made specific by "of social media on teenagers" → "the impact".',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Crime rate in this city has fallen by 20% over the past decade.",
                "correct_answer": "Incorrect",
                "wrong_answers": [],
                "explanation": '"Crime rate in this city" is specific → needs "the": "The crime rate in this city...".',
            },
        ],
    },
    {
        "rule_title": '"the" with of-phrases',
        "rule_text": (
            'When a noun is followed by an of-phrase, it almost always takes "the" '
            "because the of-phrase defines which specific instance: "
            "the impact of technology, the role of education, the number of people, "
            "the importance of health."
        ),
        "correct_example": "The role of the government in regulating the economy is debated.",
        "incorrect_example": "Role of government in regulating economy is debated.",
        "tip": '"the [noun] of [noun]" is one of the most common patterns in IELTS writing.',
        "sort_order": 8,
        "questions": [
            {
                "question_type": "fill_blank",
                "prompt": "___ number of people moving to cities is increasing every year.",
                "correct_answer": "The",
                "wrong_answers": ["A", "—", "An"],
                "explanation": '"Number of people" is an of-phrase that specifies which number → "the".',
            },
            {
                "question_type": "error_correction",
                "prompt": "Importance of higher education cannot be overstated.",
                "correct_answer": "The importance of higher education cannot be overstated.",
                "wrong_answers": [],
                "explanation": '"Importance of higher education" is an of-phrase → requires "the".',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The level of air pollution in major cities is alarming.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"The level of air pollution" correctly uses "the" with the of-phrase.',
            },
        ],
    },
    {
        "rule_title": "Articles with institutions and fixed expressions",
        "rule_text": (
            "Some nouns change meaning with or without articles in fixed phrases. "
            '"Go to school" = attend as a student (purpose). '
            '"Go to the school" = visit the building. '
            "Similar: in hospital / in the hospital, at university / at the university, "
            "go to prison / go to the prison, go to bed / go to the bed."
        ),
        "correct_example": "Many young people go to university to improve their career prospects.",
        "incorrect_example": "Many young people go to the university to improve their career prospects.",
        "tip": 'Purpose/function → no article. Physical place → "the".',
        "sort_order": 9,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct sentence about attending as a student:",
                "correct_answer": "She went to university at the age of 18.",
                "wrong_answers": [
                    "She went to the university at the age of 18.",
                    "She went to a university at the age of 18.",
                    "She went to an university at the age of 18.",
                ],
                "explanation": '"Go to university" (no article) = attend as a student, expressing purpose.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Criminals are sent to prison as a form of punishment.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"Go to prison" (no article) = be imprisoned. This refers to the purpose, not the building.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "The government plans to build ___ new school in the area. Meanwhile, children continue to go to ___ school in the neighbouring village.",
                "correct_answer": "a, —",
                "wrong_answers": ["a, the", "the, —", "—, the"],
                "explanation": 'First blank: a new school (introducing). Second blank: "go to school" = attend for education (purpose, no article).',
            },
        ],
    },
    {
        "rule_title": "Common article errors for Azerbaijani/Turkish/Russian speakers",
        "rule_text": (
            "Azerbaijani, Turkish, and Russian have no article system, leading to predictable errors: "
            '(1) Adding "the" before abstract nouns used generally: ✗ "The education is important." '
            '(2) Omitting "the" when the noun is specific: ✗ "Government should act." '
            '(3) Omitting "a/an" with singular countable nouns: ✗ "This is important issue." '
            '(4) Using "the" with general plural nouns: ✗ "The people need access to healthcare."'
        ),
        "correct_example": "Education is important. The education system in Azerbaijan needs reform.",
        "incorrect_example": "The education is important. Education system in Azerbaijan needs reform.",
        "tip": "Train yourself: general = no article; specific = the; singular countable first mention = a/an.",
        "sort_order": 10,
        "questions": [
            {
                "question_type": "error_correction",
                "prompt": "The globalisation has both positive and negative effects on the developing countries.",
                "correct_answer": "Globalisation has both positive and negative effects on developing countries.",
                "wrong_answers": [],
                "explanation": '"Globalisation" (general abstract noun) and "developing countries" (general plural) both take zero article.',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the sentence with correct article usage:",
                "correct_answer": "Access to healthcare is a fundamental human right.",
                "wrong_answers": [
                    "The access to healthcare is fundamental human right.",
                    "Access to the healthcare is the fundamental human right.",
                    "The access to the healthcare is a fundamental human right.",
                ],
                "explanation": '"Access" (general concept) → no article. "Healthcare" (general) → no article. "A fundamental human right" → singular countable, first mention.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "This is important issue that the governments must address.",
                "correct_answer": "Incorrect",
                "wrong_answers": [],
                "explanation": 'Missing "an" before "important issue" (singular countable noun). "The governments" should be "governments" (general): "This is an important issue that governments must address."',
            },
            {
                "question_type": "error_correction",
                "prompt": "The children in the developing countries often lack access to the education.",
                "correct_answer": "Children in developing countries often lack access to education.",
                "wrong_answers": [],
                "explanation": "All three nouns are used in a general sense: children (all), developing countries (all), education (general concept) — all take zero article.",
            },
        ],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# TOPIC 2: Punctuation — Commas
# ═══════════════════════════════════════════════════════════════════════════

COMMAS_TOPIC = {
    "name": "Punctuation — Commas",
    "description": "Correct comma usage in academic writing for IELTS",
}

COMMAS_RULES = [
    {
        "rule_title": "Comma after introductory adverbial clauses",
        "rule_text": (
            "When a sentence begins with a dependent adverbial clause "
            "(starting with if, when, because, although, while, since, after, before, unless, etc.), "
            "place a comma after the clause before the main clause. "
            "If the adverbial clause comes AFTER the main clause, usually no comma is needed."
        ),
        "correct_example": "Although many people oppose the idea, renewable energy is essential for the future.",
        "incorrect_example": "Although many people oppose the idea renewable energy is essential for the future.",
        "tip": "Adverbial clause first → comma before the main clause. Main clause first → usually no comma.",
        "sort_order": 1,
        "questions": [
            {
                "question_type": "correct_or_incorrect",
                "prompt": "If governments invest in public transport, traffic congestion will decrease.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": 'The introductory adverbial clause "If governments invest in public transport" is correctly followed by a comma.',
            },
            {
                "question_type": "error_correction",
                "prompt": "Because the population is ageing healthcare costs are likely to rise.",
                "correct_answer": "Because the population is ageing, healthcare costs are likely to rise.",
                "wrong_answers": [],
                "explanation": 'A comma is needed after the introductory adverbial clause "Because the population is ageing".',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence uses commas correctly?",
                "correct_answer": "When technology is used responsibly, it can greatly enhance learning.",
                "wrong_answers": [
                    "When technology is used responsibly it can greatly enhance learning.",
                    "When, technology is used responsibly, it can greatly enhance learning.",
                    "When technology is used responsibly it, can greatly enhance learning.",
                ],
                "explanation": "The introductory adverbial clause needs a comma after it, before the main clause.",
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Traffic congestion will decrease if governments invest in public transport.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": "When the adverbial clause comes after the main clause, no comma is usually needed.",
            },
        ],
    },
    {
        "rule_title": "Comma after introductory participial phrases",
        "rule_text": (
            "When a sentence begins with a participial phrase (starting with a present or past participle), "
            "always place a comma after it. These phrases describe the subject of the main clause. "
            "Examples: Having considered..., Given the evidence..., Compared to..., Speaking broadly..."
        ),
        "correct_example": "Having analysed the data, the researchers concluded that the treatment was effective.",
        "incorrect_example": "Having analysed the data the researchers concluded that the treatment was effective.",
        "tip": "Participial phrase at the start → always comma. Make sure the subject of the main clause is the one doing the action.",
        "sort_order": 2,
        "questions": [
            {
                "question_type": "error_correction",
                "prompt": "Compared to previous decades people today have greater access to information.",
                "correct_answer": "Compared to previous decades, people today have greater access to information.",
                "wrong_answers": [],
                "explanation": 'The introductory participial phrase "Compared to previous decades" must be followed by a comma.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Given the rising cost of living, many families are struggling to meet basic needs.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": 'The participial phrase "Given the rising cost of living" is correctly followed by a comma.',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence is punctuated correctly?",
                "correct_answer": "Speaking from an economic perspective, globalisation has created both winners and losers.",
                "wrong_answers": [
                    "Speaking from an economic perspective globalisation has created both winners and losers.",
                    "Speaking, from an economic perspective, globalisation has created both winners and losers.",
                    "Speaking from an economic perspective globalisation, has created both winners and losers.",
                ],
                "explanation": "The participial phrase needs one comma at the end, before the main clause.",
            },
        ],
    },
    {
        "rule_title": "Comma before coordinating conjunctions (FANBOYS)",
        "rule_text": (
            "When two independent clauses are joined by a coordinating conjunction "
            "(For, And, Nor, But, Or, Yet, So), place a comma BEFORE the conjunction. "
            "If the conjunction joins two words or phrases (not full clauses), no comma is needed."
        ),
        "correct_example": "Technology has improved communication, but it has also created new social problems.",
        "incorrect_example": "Technology has improved communication but it has also created new social problems.",
        "tip": "Two complete sentences joined by FANBOYS → comma before the conjunction. Just joining words/phrases → no comma.",
        "sort_order": 3,
        "questions": [
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Urban areas offer more job opportunities, yet they also suffer from higher pollution levels.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": 'Two independent clauses joined by "yet" — the comma before it is correct.',
            },
            {
                "question_type": "error_correction",
                "prompt": "Many students prefer online learning but others believe traditional classrooms are more effective.",
                "correct_answer": "Many students prefer online learning, but others believe traditional classrooms are more effective.",
                "wrong_answers": [],
                "explanation": 'Two independent clauses joined by "but" require a comma before the conjunction.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The government should invest in education, and healthcare.",
                "correct_answer": "Incorrect",
                "wrong_answers": [],
                "explanation": '"And" joins two nouns (education, healthcare), not two independent clauses. No comma needed: "...in education and healthcare."',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correctly punctuated sentence:",
                "correct_answer": "Renewable energy is expensive to develop, so governments must provide subsidies.",
                "wrong_answers": [
                    "Renewable energy is expensive to develop so governments must provide subsidies.",
                    "Renewable energy is expensive to develop so, governments must provide subsidies.",
                    "Renewable energy, is expensive to develop so governments must provide subsidies.",
                ],
                "explanation": 'Two independent clauses joined by "so" require a comma before it.',
            },
        ],
    },
    {
        "rule_title": "Commas with non-restrictive (non-defining) relative clauses",
        "rule_text": (
            "Non-defining relative clauses give EXTRA information about a noun that is already clearly identified. "
            "They are enclosed in commas and can be removed without changing the meaning of the sentence. "
            'They use "who", "which", or "whose" — never "that".'
        ),
        "correct_example": "The United Nations, which was founded in 1945, plays a key role in global diplomacy.",
        "incorrect_example": "The United Nations which was founded in 1945 plays a key role in global diplomacy.",
        "tip": 'Can you remove the clause and the sentence still identifies the noun? If yes → commas + "which/who". Never use "that" in non-defining clauses.',
        "sort_order": 4,
        "questions": [
            {
                "question_type": "error_correction",
                "prompt": "Solar energy which is a renewable resource has become increasingly affordable.",
                "correct_answer": "Solar energy, which is a renewable resource, has become increasingly affordable.",
                "wrong_answers": [],
                "explanation": '"Which is a renewable resource" is extra information about solar energy (already specific) → needs commas.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Finland, which consistently ranks highly in education, invests heavily in teacher training.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": 'The clause about Finland\'s ranking is extra information, correctly set off with commas and using "which".',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correctly punctuated sentence:",
                "correct_answer": "Dr Smith, who has published over 50 papers, presented the findings at the conference.",
                "wrong_answers": [
                    "Dr Smith who has published over 50 papers presented the findings at the conference.",
                    "Dr Smith, who has published over 50 papers presented the findings at the conference.",
                    "Dr Smith who has published over 50 papers, presented the findings at the conference.",
                ],
                "explanation": "Non-defining clause needs commas on BOTH sides. Dr Smith is already identified, so the clause is extra info.",
            },
        ],
    },
    {
        "rule_title": "NO comma before restrictive (defining) relative clauses",
        "rule_text": (
            "Defining relative clauses identify WHICH person or thing is meant. "
            'They are essential to the meaning and use NO commas. "That", "who", or "which" can be used, '
            'though "that" is preferred in defining clauses.'
        ),
        "correct_example": "Students who work part-time often develop better time management skills.",
        "incorrect_example": "Students, who work part-time, often develop better time management skills.",
        "tip": "If removing the clause makes the sentence vague or changes the meaning, it is defining → no commas.",
        "sort_order": 5,
        "questions": [
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Countries that invest in renewable energy tend to have lower carbon emissions.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"That invest in renewable energy" defines WHICH countries — it is essential, so no commas.',
            },
            {
                "question_type": "error_correction",
                "prompt": "People, who exercise regularly, are less likely to suffer from chronic diseases.",
                "correct_answer": "People who exercise regularly are less likely to suffer from chronic diseases.",
                "wrong_answers": [],
                "explanation": '"Who exercise regularly" defines which people — this is a defining clause that should NOT have commas.',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence is correctly punctuated?",
                "correct_answer": "The policies that were introduced last year have reduced unemployment.",
                "wrong_answers": [
                    "The policies, that were introduced last year, have reduced unemployment.",
                    "The policies, that were introduced last year have reduced unemployment.",
                    "The policies that were introduced last year, have reduced unemployment.",
                ],
                "explanation": '"That were introduced last year" is a defining clause identifying which policies — no commas needed.',
            },
        ],
    },
    {
        "rule_title": "Comma after transition words and phrases",
        "rule_text": (
            "When a sentence begins with a transition word or phrase, follow it with a comma. "
            "Common transitions: However, Furthermore, Moreover, In addition, Nevertheless, "
            "On the other hand, For example, In contrast, As a result, Consequently, Therefore."
        ),
        "correct_example": "Furthermore, the study found a strong correlation between diet and academic performance.",
        "incorrect_example": "Furthermore the study found a strong correlation between diet and academic performance.",
        "tip": "Transition word at the start of a sentence → always comma after it.",
        "sort_order": 6,
        "questions": [
            {
                "question_type": "error_correction",
                "prompt": "However many experts disagree with this approach to urban planning.",
                "correct_answer": "However, many experts disagree with this approach to urban planning.",
                "wrong_answers": [],
                "explanation": '"However" as a transition word at the start of a sentence must be followed by a comma.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "In addition, governments should regulate social media platforms more strictly.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"In addition" is a transition phrase correctly followed by a comma.',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence is correctly punctuated?",
                "correct_answer": "On the other hand, some argue that traditional teaching methods are more effective.",
                "wrong_answers": [
                    "On the other hand some argue that traditional teaching methods are more effective.",
                    "On the other hand some argue, that traditional teaching methods are more effective.",
                    "On, the other hand, some argue that traditional teaching methods are more effective.",
                ],
                "explanation": '"On the other hand" is a complete transition phrase that needs a comma after it.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "The experiment was successful. As a result___ the findings were published in a major journal.",
                "correct_answer": ",",
                "wrong_answers": [".", ";", "—"],
                "explanation": '"As a result" is a transition phrase and should be followed by a comma.',
            },
        ],
    },
    {
        "rule_title": "Serial comma (Oxford comma) in lists",
        "rule_text": (
            "When listing three or more items, place a comma after each item, including before "
            'the final conjunction (and/or). This is called the Oxford comma. '
            "In academic writing, the Oxford comma prevents ambiguity. "
            '"The study covered health, education, and employment." (clear: three separate topics)'
        ),
        "correct_example": "The government should focus on healthcare, education, and infrastructure.",
        "incorrect_example": "The government should focus on healthcare, education and infrastructure.",
        "tip": "In IELTS academic writing, always use the Oxford comma to be safe and clear.",
        "sort_order": 7,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence uses the serial comma correctly?",
                "correct_answer": "The main causes of pollution are factories, vehicles, and deforestation.",
                "wrong_answers": [
                    "The main causes of pollution are factories vehicles and deforestation.",
                    "The main causes of pollution are, factories, vehicles, and deforestation.",
                    "The main causes of pollution are factories, vehicles and, deforestation.",
                ],
                "explanation": "Items in a list need commas between them, including before the final 'and' (Oxford comma).",
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The study examined the effects of diet, exercise, and sleep on academic performance.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": "Three items listed with commas after each, including the Oxford comma before 'and' — correct.",
            },
            {
                "question_type": "error_correction",
                "prompt": "Urban planning must consider housing transportation and green spaces.",
                "correct_answer": "Urban planning must consider housing, transportation, and green spaces.",
                "wrong_answers": [],
                "explanation": "A list of three items needs commas: housing, transportation, and green spaces.",
            },
        ],
    },
    {
        "rule_title": "NO comma between subject and verb",
        "rule_text": (
            "Never place a comma between the subject and its verb, even when the subject "
            "is long or complex. This is a common error in IELTS essays, especially with "
            "long noun phrases or that-clauses as subjects."
        ),
        "correct_example": "The idea that governments should provide free healthcare is widely supported.",
        "incorrect_example": "The idea that governments should provide free healthcare, is widely supported.",
        "tip": "No matter how long the subject is, do not separate it from its verb with a comma.",
        "sort_order": 8,
        "questions": [
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The growing number of elderly people in developed countries, is putting pressure on healthcare systems.",
                "correct_answer": "Incorrect",
                "wrong_answers": [],
                "explanation": "The comma between the subject ('The growing number of elderly people in developed countries') and the verb ('is putting') must be removed.",
            },
            {
                "question_type": "error_correction",
                "prompt": "Whether students should be required to wear uniforms, remains a controversial topic.",
                "correct_answer": "Whether students should be required to wear uniforms remains a controversial topic.",
                "wrong_answers": [],
                "explanation": "The subject is the entire clause 'Whether students should be required to wear uniforms' — no comma before the verb 'remains'.",
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The belief that technology will solve all environmental problems is dangerously naive.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": "Despite the long subject, there is correctly no comma between it and the verb 'is'.",
            },
        ],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# TOPIC 3: Conditionals
# ═══════════════════════════════════════════════════════════════════════════

CONDITIONALS_TOPIC = {
    "name": "Conditionals",
    "description": "Zero, first, second, third, and mixed conditionals for IELTS writing and speaking",
}

CONDITIONALS_RULES = [
    {
        "rule_title": "Zero conditional — general truths and facts",
        "rule_text": (
            "Use the zero conditional for things that are ALWAYS true — scientific facts, "
            "general truths, and natural consequences. "
            "Structure: If/When + present simple, present simple. "
            "Both clauses use present simple."
        ),
        "correct_example": "If water reaches 100°C, it boils.",
        "incorrect_example": "If water reaches 100°C, it will boil.",
        "tip": "Zero conditional = always true, no exceptions. Both sides are present simple.",
        "sort_order": 1,
        "questions": [
            {
                "question_type": "fill_blank",
                "prompt": "If air quality ___ (decline), respiratory diseases ___ (increase) in urban populations.",
                "correct_answer": "declines, increase",
                "wrong_answers": ["will decline, will increase", "declined, increased", "declines, will increase"],
                "explanation": "Zero conditional (general truth): If + present simple, present simple.",
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct zero conditional sentence:",
                "correct_answer": "When people lack access to education, poverty rates remain high.",
                "wrong_answers": [
                    "When people lack access to education, poverty rates will remain high.",
                    "When people lacked access to education, poverty rates remained high.",
                    "When people would lack access to education, poverty rates remain high.",
                ],
                "explanation": "Zero conditional uses present simple in both clauses for general truths.",
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "If a country invests in infrastructure, its economy grows.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": "This is a correct zero conditional — a general truth with present simple in both clauses.",
            },
        ],
    },
    {
        "rule_title": "First conditional — real/likely future situations",
        "rule_text": (
            "Use the first conditional for situations that are LIKELY to happen in the future. "
            "Structure: If + present simple, will + infinitive. "
            "The if-clause uses present simple (NOT 'will'), and the result clause uses will/can/may."
        ),
        "correct_example": "If the government raises taxes, consumer spending will decrease.",
        "incorrect_example": "If the government will raise taxes, consumer spending will decrease.",
        "tip": 'Never use "will" in the if-clause of a first conditional.',
        "sort_order": 2,
        "questions": [
            {
                "question_type": "error_correction",
                "prompt": "If the government will ban single-use plastics, pollution will decrease significantly.",
                "correct_answer": "If the government bans single-use plastics, pollution will decrease significantly.",
                "wrong_answers": [],
                "explanation": 'The if-clause must use present simple, not "will": "If the government bans...".',
            },
            {
                "question_type": "fill_blank",
                "prompt": "If universities ___ (reduce) tuition fees, more students ___ (be able to) afford higher education.",
                "correct_answer": "reduce, will be able to",
                "wrong_answers": ["will reduce, will be able to", "reduced, would be able to", "reduce, would be able to"],
                "explanation": "First conditional: If + present simple, will + infinitive.",
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "If global temperatures continue to rise, sea levels will threaten coastal cities.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": "Correct first conditional: present simple in the if-clause, will in the result clause.",
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct first conditional:",
                "correct_answer": "If more people use public transport, carbon emissions will fall.",
                "wrong_answers": [
                    "If more people will use public transport, carbon emissions will fall.",
                    "If more people used public transport, carbon emissions will fall.",
                    "If more people use public transport, carbon emissions fall.",
                ],
                "explanation": "First conditional: If + present simple (use), will + infinitive (will fall).",
            },
        ],
    },
    {
        "rule_title": "Second conditional — hypothetical present/future",
        "rule_text": (
            "Use the second conditional for IMAGINARY or UNLIKELY situations in the present or future. "
            "Structure: If + past simple, would + infinitive. "
            'Use "were" instead of "was" for all persons in formal writing (If I were..., If it were...).'
        ),
        "correct_example": "If every country invested equally in education, global inequality would decrease.",
        "incorrect_example": "If every country invests equally in education, global inequality would decrease.",
        "tip": "Past tense in the if-clause does NOT mean past time — it signals unreality/hypothesis.",
        "sort_order": 3,
        "questions": [
            {
                "question_type": "fill_blank",
                "prompt": "If the government ___ (provide) free childcare, more women ___ (enter) the workforce.",
                "correct_answer": "provided, would enter",
                "wrong_answers": ["provides, will enter", "will provide, would enter", "provided, will enter"],
                "explanation": "Second conditional (hypothetical): If + past simple, would + infinitive.",
            },
            {
                "question_type": "error_correction",
                "prompt": "If every person recycled properly, the environment will benefit enormously.",
                "correct_answer": "If every person recycled properly, the environment would benefit enormously.",
                "wrong_answers": [],
                "explanation": 'Second conditional requires "would" in the result clause, not "will".',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence correctly uses the second conditional?",
                "correct_answer": "If public transport were free, fewer people would drive to work.",
                "wrong_answers": [
                    "If public transport was free, fewer people will drive to work.",
                    "If public transport is free, fewer people would drive to work.",
                    "If public transport will be free, fewer people would drive to work.",
                ],
                "explanation": 'Second conditional: If + past simple (were — formal), would + infinitive.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "If I were the minister of education, I would make university education free for all citizens.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": 'Correct second conditional with formal "were" for hypothetical situation.',
            },
        ],
    },
    {
        "rule_title": "Third conditional — hypothetical past",
        "rule_text": (
            "Use the third conditional for situations that did NOT happen in the past. "
            "We imagine a different past and its imagined result. "
            "Structure: If + past perfect, would have + past participle."
        ),
        "correct_example": "If governments had invested in renewable energy earlier, climate change would not have become so severe.",
        "incorrect_example": "If governments invested in renewable energy earlier, climate change would not become so severe.",
        "tip": "Third conditional = regret, reflection, or analysis about the past. Both clauses signal past unreality.",
        "sort_order": 4,
        "questions": [
            {
                "question_type": "fill_blank",
                "prompt": "If the company ___ (implement) safety measures sooner, the accident ___ (not occur).",
                "correct_answer": "had implemented, would not have occurred",
                "wrong_answers": [
                    "implemented, would not occur",
                    "had implemented, will not have occurred",
                    "would have implemented, had not occurred",
                ],
                "explanation": "Third conditional: If + past perfect, would have + past participle.",
            },
            {
                "question_type": "error_correction",
                "prompt": "If the government invested more in education in the 1990s, the country would be more competitive today.",
                "correct_answer": "If the government had invested more in education in the 1990s, the country would be more competitive today.",
                "wrong_answers": [],
                "explanation": "Referring to an unreal past situation requires past perfect in the if-clause: 'had invested'. Note: the result clause uses 'would be' (present result) — this is actually a mixed conditional.",
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct third conditional:",
                "correct_answer": "If the city had built more parks, residents would have enjoyed a better quality of life.",
                "wrong_answers": [
                    "If the city built more parks, residents would enjoy a better quality of life.",
                    "If the city had built more parks, residents will have enjoyed a better quality of life.",
                    "If the city would have built more parks, residents had enjoyed a better quality of life.",
                ],
                "explanation": "Third conditional: If + past perfect (had built), would have + past participle (would have enjoyed).",
            },
        ],
    },
    {
        "rule_title": "Mixed conditionals",
        "rule_text": (
            "Mixed conditionals combine different time references between the if-clause and the result clause. "
            "Type 1 — Past condition → Present result: If + past perfect, would + infinitive. "
            '"If they had invested in education [past], the economy would be stronger [now]." '
            "Type 2 — Present condition → Past result: If + past simple, would have + past participle. "
            '"If he were more qualified [now], he would have been hired [then]."'
        ),
        "correct_example": "If the government had regulated emissions earlier, air quality would be better today.",
        "incorrect_example": "If the government had regulated emissions earlier, air quality would have been better today.",
        "tip": "The key is recognising that the TIME in the if-clause and the result clause are DIFFERENT.",
        "sort_order": 5,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct mixed conditional (past cause → present result):",
                "correct_answer": "If they had built the metro system decades ago, the city would have less traffic now.",
                "wrong_answers": [
                    "If they built the metro system decades ago, the city would have less traffic now.",
                    "If they had built the metro system decades ago, the city would have had less traffic now.",
                    "If they build the metro system decades ago, the city will have less traffic now.",
                ],
                "explanation": "Past condition (had built) → present result (would have) — a mixed conditional linking past to present.",
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "If the country were richer, it would have invested more in healthcare last year.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": "Mixed conditional: present condition (were richer — now) → past result (would have invested — last year).",
            },
            {
                "question_type": "fill_blank",
                "prompt": "If scientists ___ (discover) a cure earlier, millions of lives ___ (be saved) today.",
                "correct_answer": "had discovered, would be saved",
                "wrong_answers": [
                    "discovered, would be saved",
                    "had discovered, would have been saved",
                    "discover, will be saved",
                ],
                "explanation": "Mixed conditional: past condition (had discovered) → present result (would be saved today).",
            },
        ],
    },
    {
        "rule_title": "Inverted conditionals without 'if'",
        "rule_text": (
            'In formal/academic writing, "if" can be dropped by inverting the subject and auxiliary. '
            "This sounds more sophisticated and is valued in IELTS band 7+ writing. "
            "Were + subject (= If ... were): Were the government to invest... "
            "Had + subject + past participle (= If ... had): Had they implemented... "
            "Should + subject + infinitive (= If ... should): Should this trend continue..."
        ),
        "correct_example": "Were the government to increase funding, educational outcomes would improve.",
        "incorrect_example": "Was the government to increase funding, educational outcomes would improve.",
        "tip": 'Inversion = drop "if" + move the auxiliary before the subject. Great for IELTS band 7+ essays.',
        "sort_order": 6,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct inverted conditional:",
                "correct_answer": "Had the authorities acted sooner, the environmental damage could have been prevented.",
                "wrong_answers": [
                    "Have the authorities acted sooner, the environmental damage could have been prevented.",
                    "Had the authorities act sooner, the environmental damage could have been prevented.",
                    "If had the authorities acted sooner, the environmental damage could have been prevented.",
                ],
                "explanation": "Inverted third conditional: Had + subject + past participle (Had the authorities acted...).",
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Should this trend continue, the healthcare system will face unprecedented challenges.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": "Correct inverted first conditional: Should + subject + infinitive = If this trend should continue.",
            },
            {
                "question_type": "error_correction",
                "prompt": "Was the government to invest more in renewable energy, carbon emissions would decrease.",
                "correct_answer": "Were the government to invest more in renewable energy, carbon emissions would decrease.",
                "wrong_answers": [],
                "explanation": 'Inverted conditionals always use "were", never "was", regardless of the subject.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "___ this policy ___ (implement), unemployment rates would fall dramatically.",
                "correct_answer": "Were, to be implemented",
                "wrong_answers": [
                    "Was, to be implemented",
                    "Should, to be implemented",
                    "Had, to be implemented",
                ],
                "explanation": "Inverted second conditional: Were + subject + to + infinitive.",
            },
        ],
    },
    {
        "rule_title": 'Common error: "would" in the if-clause',
        "rule_text": (
            'A very common IELTS error is using "would" in the if-clause. '
            '"Would" belongs in the RESULT clause, never in the if-clause. '
            'Incorrect: "If the government would invest..." → Correct: "If the government invested..." '
            "This error often comes from translating directly from languages like Turkish, Russian, or Azerbaijani."
        ),
        "correct_example": "If governments invested more in public health, chronic diseases would decline.",
        "incorrect_example": "If governments would invest more in public health, chronic diseases would decline.",
        "tip": '"Would" goes in the result clause only. The if-clause uses present simple (1st) or past simple (2nd) or past perfect (3rd).',
        "sort_order": 7,
        "questions": [
            {
                "question_type": "error_correction",
                "prompt": "If people would use less plastic, ocean pollution would decrease.",
                "correct_answer": "If people used less plastic, ocean pollution would decrease.",
                "wrong_answers": [],
                "explanation": '"Would" cannot appear in the if-clause. Second conditional: If + past simple (used).',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "If companies would offer flexible working hours, employee satisfaction would increase.",
                "correct_answer": "Incorrect",
                "wrong_answers": [],
                "explanation": '"Would" is incorrectly placed in the if-clause. Correct: "If companies offered flexible working hours...".',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence is grammatically correct?",
                "correct_answer": "If the city built more cycle lanes, air quality would improve.",
                "wrong_answers": [
                    "If the city would build more cycle lanes, air quality would improve.",
                    "If the city would build more cycle lanes, air quality will improve.",
                    "If the city will build more cycle lanes, air quality would improve.",
                ],
                "explanation": "Second conditional: If + past simple (built), would + infinitive (would improve).",
            },
        ],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# TOPIC 4: Relative Clauses
# ═══════════════════════════════════════════════════════════════════════════

RELATIVE_CLAUSES_TOPIC = {
    "name": "Relative Clauses",
    "description": "Defining and non-defining relative clauses, reduction, and common errors",
}

RELATIVE_CLAUSES_RULES = [
    {
        "rule_title": "Defining vs non-defining relative clauses",
        "rule_text": (
            "DEFINING clauses identify which noun we mean — they are essential. No commas. "
            '"Students who study hard get better results." (which students?) '
            "NON-DEFINING clauses add extra info about an already-identified noun. Commas required. "
            '"My sister, who lives in London, is a doctor." (sister is already identified)'
        ),
        "correct_example": "Countries that invest in education tend to have higher GDP. / Japan, which has an ageing population, faces unique economic challenges.",
        "incorrect_example": "Countries, that invest in education, tend to have higher GDP. / Japan which has an ageing population faces unique economic challenges.",
        "tip": "Ask: Is the clause essential to know WHICH one? Yes → defining (no commas). No → non-defining (commas).",
        "sort_order": 1,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correctly punctuated sentence:",
                "correct_answer": "People who live in rural areas often have limited access to healthcare.",
                "wrong_answers": [
                    "People, who live in rural areas, often have limited access to healthcare.",
                    "People, who live in rural areas often have limited access to healthcare.",
                    "People who live in rural areas, often have limited access to healthcare.",
                ],
                "explanation": '"Who live in rural areas" identifies WHICH people — defining clause, no commas.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Beijing, which is the capital of China, has experienced rapid urbanisation.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": "Beijing is already identified; the clause adds extra info — non-defining, commas correct.",
            },
            {
                "question_type": "error_correction",
                "prompt": "The teacher, who inspired me the most, was my high school English teacher.",
                "correct_answer": "The teacher who inspired me the most was my high school English teacher.",
                "wrong_answers": [],
                "explanation": '"Who inspired me the most" identifies WHICH teacher — this is a defining clause and should NOT have commas.',
            },
        ],
    },
    {
        "rule_title": "Who, which, and that — usage rules",
        "rule_text": (
            '"Who" is for people. "Which" is for things. "That" can replace both in DEFINING clauses only. '
            '"That" is NEVER used in non-defining clauses. '
            "In formal academic writing, 'which' is preferred over 'that' for things in some styles, "
            "but both are acceptable in IELTS."
        ),
        "correct_example": "The students who passed the exam celebrated. / The policy that was introduced has been effective.",
        "incorrect_example": "The students which passed the exam celebrated. / London, that is the capital of the UK, is multicultural.",
        "tip": 'People → who/that. Things → which/that. Non-defining → never "that".',
        "sort_order": 2,
        "questions": [
            {
                "question_type": "error_correction",
                "prompt": "The researchers which conducted the study found surprising results.",
                "correct_answer": "The researchers who conducted the study found surprising results.",
                "wrong_answers": [],
                "explanation": '"Which" cannot be used for people — use "who" or "that".',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The WHO, that was founded in 1948, coordinates international health efforts.",
                "correct_answer": "Incorrect",
                "wrong_answers": [],
                "explanation": '"That" cannot be used in non-defining clauses. Correct: "The WHO, which was founded in 1948,...".',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct sentence:",
                "correct_answer": "The factors that contribute to climate change are well documented.",
                "wrong_answers": [
                    "The factors who contribute to climate change are well documented.",
                    "The factors, that contribute to climate change, are well documented.",
                    "The factors whom contribute to climate change are well documented.",
                ],
                "explanation": '"That" is correct for things in defining clauses (no commas).',
            },
        ],
    },
    {
        "rule_title": "Relative clauses with prepositions",
        "rule_text": (
            "When a relative clause contains a preposition, you have two options: "
            "Formal: preposition + which/whom — 'the city in which he was born' "
            "Informal: preposition at the end — 'the city which he was born in' "
            "In IELTS writing, the formal style (preposition + which) demonstrates higher-level grammar."
        ),
        "correct_example": "The country in which the study was conducted has a tropical climate.",
        "incorrect_example": "The country in that the study was conducted has a tropical climate.",
        "tip": '"In which", "for which", "to whom" — this formal structure impresses IELTS examiners. Never use "in that".',
        "sort_order": 3,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Choose the most formal and correct option:",
                "correct_answer": "The extent to which technology affects learning is still debated.",
                "wrong_answers": [
                    "The extent to that technology affects learning is still debated.",
                    "The extent which technology affects learning to is still debated.",
                    "The extent to who technology affects learning is still debated.",
                ],
                "explanation": '"To which" is the correct formal relative clause with preposition. "To that" is never correct.',
            },
            {
                "question_type": "error_correction",
                "prompt": "The reason for that many students fail is a lack of preparation.",
                "correct_answer": "The reason for which many students fail is a lack of preparation.",
                "wrong_answers": [],
                "explanation": '"For that" is not grammatical — use "for which" with preposition + relative pronoun.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The community in which the programme was implemented saw a 30% drop in crime.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"In which" is the correct formal construction for a relative clause with a preposition.',
            },
        ],
    },
    {
        "rule_title": "Reduced relative clauses (participle clauses)",
        "rule_text": (
            "You can shorten a relative clause by removing the relative pronoun and the auxiliary verb, "
            "leaving a participle. This makes writing more concise and is valued in IELTS. "
            'Active: "students who study abroad" → "students studying abroad" '
            'Passive: "policies which were introduced last year" → "policies introduced last year"'
        ),
        "correct_example": "The number of people living in urban areas is increasing rapidly.",
        "incorrect_example": "The number of people who are living in urban areas is increasing rapidly.",
        "tip": "Reduced clauses sound more academic and save word count. Active → -ing. Passive → past participle.",
        "sort_order": 4,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence uses a reduced relative clause?",
                "correct_answer": "Measures taken by the government have reduced poverty.",
                "wrong_answers": [
                    "Measures that were taken by the government have reduced poverty.",
                    "Measures which the government took have reduced poverty.",
                    "Measures that the government has taken have reduced poverty.",
                ],
                "explanation": '"Measures taken by the government" is a reduced form of "measures that were taken by the government".',
            },
            {
                "question_type": "error_correction",
                "prompt": "The data which was collected during the survey indicates a positive trend.",
                "correct_answer": "The data collected during the survey indicates a positive trend.",
                "wrong_answers": [],
                "explanation": "Reduced relative clause: remove 'which was' → 'The data collected during the survey...'.",
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Countries experiencing rapid urbanisation face unique infrastructure challenges.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"Countries experiencing..." is a correctly reduced form of "countries that are experiencing...".',
            },
            {
                "question_type": "fill_blank",
                "prompt": "The solutions ___ at the conference could help address climate change. (propose)",
                "correct_answer": "proposed",
                "wrong_answers": ["proposing", "which proposing", "to propose"],
                "explanation": "Passive reduced clause: 'solutions (that were) proposed at the conference' → past participle.",
            },
        ],
    },
    {
        "rule_title": '"Whose" for possession in relative clauses',
        "rule_text": (
            '"Whose" shows possession and can be used for both people and things. '
            "It replaces possessive forms (his, her, its, their) in relative clauses. "
            '"The country whose economy depends on tourism..." '
            '"Students whose parents support their education..."'
        ),
        "correct_example": "Countries whose economies rely on fossil fuels face difficult transitions.",
        "incorrect_example": "Countries who their economies rely on fossil fuels face difficult transitions.",
        "tip": '"Whose" = the ____ of which/whom. It works for people AND things in IELTS writing.',
        "sort_order": 5,
        "questions": [
            {
                "question_type": "error_correction",
                "prompt": "The city who its population has doubled needs more housing.",
                "correct_answer": "The city whose population has doubled needs more housing.",
                "wrong_answers": [],
                "explanation": '"Whose" replaces "who its" to show possession.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "Students ___ first language is not English may need additional support.",
                "correct_answer": "whose",
                "wrong_answers": ["who", "which", "that"],
                "explanation": '"Whose" shows possession — the first language belongs to the students.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Families whose income falls below the poverty line are eligible for government support.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"Whose income" correctly shows possession in this defining relative clause.',
            },
        ],
    },
    {
        "rule_title": "Common error: unnecessary pronoun after relative pronoun",
        "rule_text": (
            "A very common error is adding an extra pronoun inside the relative clause. "
            'The relative pronoun (who/which/that) already replaces the pronoun. '
            '✗ "The book which I read it was fascinating." '
            '✓ "The book which I read was fascinating." '
            "This error is extremely common for speakers of Arabic, Turkish, Azerbaijani, and Farsi."
        ),
        "correct_example": "The city that I visited last year has changed dramatically.",
        "incorrect_example": "The city that I visited it last year has changed dramatically.",
        "tip": 'The relative pronoun replaces "it/them/him/her". Never double up.',
        "sort_order": 6,
        "questions": [
            {
                "question_type": "error_correction",
                "prompt": "The policy which the government introduced it has been very effective.",
                "correct_answer": "The policy which the government introduced has been very effective.",
                "wrong_answers": [],
                "explanation": 'Remove the unnecessary "it" — "which" already serves as the object.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The school that we attended has been renovated recently.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": 'No extra pronoun after "attended" — the relative pronoun "that" is sufficient.',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct sentence:",
                "correct_answer": "The challenges that developing countries face are complex.",
                "wrong_answers": [
                    "The challenges that developing countries face them are complex.",
                    "The challenges which developing countries face them are complex.",
                    "The challenges that developing countries they face are complex.",
                ],
                "explanation": "No extra pronoun is needed — 'that' already serves as the object of 'face'.",
            },
            {
                "question_type": "error_correction",
                "prompt": "The people who we interviewed them expressed concern about rising costs.",
                "correct_answer": "The people who we interviewed expressed concern about rising costs.",
                "wrong_answers": [],
                "explanation": 'Remove "them" — "who" already replaces the object pronoun.',
            },
        ],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# TOPIC 5: High-Band Sentence Structures
# ═══════════════════════════════════════════════════════════════════════════

HIGH_BAND_TOPIC = {
    "name": "High-Band Sentence Structures",
    "description": "Advanced sentence structures for achieving IELTS band 7+ in writing",
}

HIGH_BAND_RULES = [
    {
        "rule_title": 'Cleft sentences: "It is X that..." and "What...is..."',
        "rule_text": (
            "Cleft sentences split a simple sentence to emphasise one part. "
            '"It is [focus] that [rest of sentence]." — emphasises a specific element. '
            '"What [clause] is [focus]." — emphasises the main point. '
            "These structures show grammatical range and help you make strong topic sentences."
        ),
        "correct_example": "It is education that holds the key to reducing inequality. / What makes this issue significant is its impact on future generations.",
        "incorrect_example": "Education holds the key to reducing inequality.",
        "tip": 'Use "It is...that" to spotlight a cause/factor. Use "What...is" to build to a conclusion.',
        "sort_order": 1,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence uses a cleft structure?",
                "correct_answer": "It is the lack of funding that prevents schools from improving.",
                "wrong_answers": [
                    "The lack of funding prevents schools from improving.",
                    "Schools cannot improve due to a lack of funding.",
                    "Funding is lacking, so schools cannot improve.",
                ],
                "explanation": '"It is [the lack of funding] that [prevents schools from improving]" is a cleft sentence emphasising the cause.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "What ___ this problem particularly concerning ___ its effect on young children.",
                "correct_answer": "makes, is",
                "wrong_answers": ["make, are", "is making, was", "made, is"],
                "explanation": '"What makes X is Y" — a cleft sentence pattern. "What" takes third-person singular "makes".',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "It is through international cooperation that climate change can be addressed effectively.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": 'This is a correct cleft sentence: "It is [through international cooperation] that [climate change can be addressed]".',
            },
        ],
    },
    {
        "rule_title": "Participle clauses for conciseness",
        "rule_text": (
            "Participle clauses replace full subordinate clauses to make writing more concise and academic. "
            '"Having considered the evidence, one can conclude..." (= After we have considered...) '
            '"Given the current trends, it is likely that..." (= If we consider...) '
            '"Faced with growing inequality, governments must act." (= Because they face...)'
        ),
        "correct_example": "Having analysed the data from multiple studies, the researchers found a clear correlation.",
        "incorrect_example": "After the researchers had analysed the data from multiple studies, they found a clear correlation.",
        "tip": "Start sentences with participle clauses for a more academic tone. -ing = active, -ed = passive.",
        "sort_order": 2,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence uses a participle clause correctly?",
                "correct_answer": "Considering the evidence, it seems clear that early intervention is more effective.",
                "wrong_answers": [
                    "When we are considering the evidence, it seems clear that early intervention is more effective.",
                    "If we consider the evidence, it seems clear that early intervention is more effective.",
                    "The evidence is considered, so early intervention is more effective.",
                ],
                "explanation": '"Considering the evidence" is a participle clause replacing a full subordinate clause.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "___ (face) with limited resources, developing nations must prioritise their spending carefully.",
                "correct_answer": "Faced",
                "wrong_answers": ["Facing", "Having faced", "To face"],
                "explanation": '"Faced with" (passive participle) = because they are faced with. The subject (developing nations) receives the action.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Having examined the long-term effects, the committee recommended a change in policy.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"Having examined" is a perfect participle clause showing the action was completed before the main clause.',
            },
        ],
    },
    {
        "rule_title": 'Nominal that-clauses: "The fact that..."',
        "rule_text": (
            "A that-clause can act as a noun (subject or object). "
            "Common patterns: 'The fact that X suggests/indicates/implies Y', "
            "'The notion that X is supported by Y', 'It is evident that X'. "
            "These structures allow you to present evidence and draw conclusions formally."
        ),
        "correct_example": "The fact that unemployment has risen sharply suggests that current policies are ineffective.",
        "incorrect_example": "Unemployment has risen sharply. This suggests current policies are ineffective.",
        "tip": '"The fact that..." turns a full sentence into a noun phrase — great for complex arguments.',
        "sort_order": 3,
        "questions": [
            {
                "question_type": "fill_blank",
                "prompt": "The fact ___ many graduates cannot find employment ___ that the education system needs reform.",
                "correct_answer": "that, suggests",
                "wrong_answers": ["which, suggesting", "that, to suggest", "—, suggests"],
                "explanation": '"The fact that [clause] suggests [conclusion]" — a nominal that-clause used as the subject.',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence uses a nominal that-clause correctly?",
                "correct_answer": "The notion that technology always improves quality of life is increasingly being questioned.",
                "wrong_answers": [
                    "The notion of technology always improves quality of life is increasingly being questioned.",
                    "The notion which technology always improves quality of life is increasingly being questioned.",
                    "That technology always improves quality of life, the notion is increasingly being questioned.",
                ],
                "explanation": '"The notion that [clause]" uses a that-clause to define what the notion is.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The fact that renewable energy costs have fallen dramatically makes the transition to green energy more feasible.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"The fact that [clause]" correctly acts as the subject, followed by the verb "makes".',
            },
        ],
    },
    {
        "rule_title": "Passive reporting structures",
        "rule_text": (
            "Passive reporting structures attribute ideas without naming a specific source. "
            "They are essential for academic tone. "
            "Common patterns: 'It has been argued/suggested/claimed that...', "
            "'X is widely regarded as...', 'X is generally considered to be...', "
            "'It is commonly believed that...'"
        ),
        "correct_example": "It has been argued that stricter regulations are needed to protect the environment.",
        "incorrect_example": "People argue that stricter regulations are needed to protect the environment.",
        "tip": "Passive reporting = academic distance. It shows you can discuss ideas objectively, a key IELTS skill.",
        "sort_order": 4,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence uses a passive reporting structure?",
                "correct_answer": "It is widely acknowledged that access to clean water is a basic human right.",
                "wrong_answers": [
                    "Everyone knows that access to clean water is a basic human right.",
                    "People acknowledge that access to clean water is a basic human right.",
                    "We all know access to clean water is a basic human right.",
                ],
                "explanation": '"It is widely acknowledged that..." is a passive reporting structure — impersonal and academic.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "It ___ been ___ that social media has a negative impact on mental health.",
                "correct_answer": "has, suggested",
                "wrong_answers": ["have, suggesting", "is, suggest", "was, suggesting"],
                "explanation": '"It has been suggested that..." — passive reporting structure in present perfect.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Education is generally considered to be the most effective way to reduce poverty.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"X is generally considered to be..." is a correct passive reporting structure.',
            },
            {
                "question_type": "error_correction",
                "prompt": "People commonly believe that economic growth is more important than environmental protection.",
                "correct_answer": "It is commonly believed that economic growth is more important than environmental protection.",
                "wrong_answers": [],
                "explanation": 'Converting to passive reporting: "People commonly believe" → "It is commonly believed".',
            },
        ],
    },
    {
        "rule_title": 'Double comparatives: "The more X, the more Y"',
        "rule_text": (
            "Double comparatives show a proportional relationship between two things. "
            "Structure: The + comparative + subject + verb, the + comparative + subject + verb. "
            '"The more a government invests in education, the stronger its economy becomes." '
            "This structure is sophisticated and demonstrates grammatical range."
        ),
        "correct_example": "The more people rely on technology, the less they develop critical thinking skills.",
        "incorrect_example": "More people rely on technology, less they develop critical thinking skills.",
        "tip": 'Both halves need "the" + comparative. This structure shows cause-effect elegantly.',
        "sort_order": 5,
        "questions": [
            {
                "question_type": "fill_blank",
                "prompt": "The ___ a city invests in public transport, the ___ its traffic congestion becomes.",
                "correct_answer": "more, less",
                "wrong_answers": ["most, least", "much, less", "more, least"],
                "explanation": 'Double comparative: "The more X, the less Y" — showing inverse proportional relationship.',
            },
            {
                "question_type": "error_correction",
                "prompt": "More students study abroad, more they appreciate cultural diversity.",
                "correct_answer": "The more students study abroad, the more they appreciate cultural diversity.",
                "wrong_answers": [],
                "explanation": 'Both halves need "the" before the comparative: "The more...the more...".',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "The higher the level of education in a country, the lower its crime rate tends to be.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": 'Correct double comparative: "The higher...the lower..." with "the" in both halves.',
            },
        ],
    },
    {
        "rule_title": "Concessive clauses for balanced arguments",
        "rule_text": (
            "Concessive clauses acknowledge the opposing view before presenting your own. "
            "They demonstrate balanced, critical thinking — essential for IELTS band 7+. "
            "Patterns: 'While it could be argued that X, Y remains true.', "
            "'Much as X may seem beneficial, Y suggests otherwise.', "
            "'Notwithstanding the fact that X, Y.'"
        ),
        "correct_example": "While it could be argued that technology improves productivity, the evidence suggests it also increases stress.",
        "incorrect_example": "Technology improves productivity, but it also increases stress.",
        "tip": "Concessive clauses show the examiner you can weigh both sides — a key Band 7+ skill.",
        "sort_order": 6,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence uses a concessive clause?",
                "correct_answer": "Much as urbanisation may drive economic growth, it also leads to overcrowding and pollution.",
                "wrong_answers": [
                    "Urbanisation drives economic growth but it also leads to overcrowding and pollution.",
                    "Urbanisation leads to overcrowding, and it also drives economic growth.",
                    "Although urbanisation, it drives economic growth and leads to overcrowding.",
                ],
                "explanation": '"Much as X may [verb]" is a sophisticated concessive clause that acknowledges one side before the counter-argument.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "___ it could be argued ___ homework develops self-discipline, excessive homework can harm students' well-being.",
                "correct_answer": "While, that",
                "wrong_answers": ["Although, —", "Despite, that", "However, that"],
                "explanation": '"While it could be argued that..." is a standard concessive clause pattern.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Notwithstanding the potential benefits of social media, its impact on mental health cannot be ignored.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"Notwithstanding the [noun phrase]" is a formal concessive structure — grammatically correct and very academic.',
            },
        ],
    },
    {
        "rule_title": 'Inverted structures for emphasis: "Not only...but also", "Rarely does..."',
        "rule_text": (
            "Inversion (auxiliary before subject) adds emphasis and sophistication. "
            "Common patterns: 'Not only does X, but it also Y.', "
            "'Rarely does X happen without Y.', 'Never before has X been so Y.', "
            "'Only by doing X can we achieve Y.', 'Under no circumstances should X.'"
        ),
        "correct_example": "Not only does technology improve communication, but it also enhances access to education.",
        "incorrect_example": "Not only technology improves communication, but it also enhances access to education.",
        "tip": 'After negative/restrictive adverbs (not only, rarely, never, only), invert the subject and auxiliary verb.',
        "sort_order": 7,
        "questions": [
            {
                "question_type": "error_correction",
                "prompt": "Not only pollution affects physical health, but it also damages the environment.",
                "correct_answer": "Not only does pollution affect physical health, but it also damages the environment.",
                "wrong_answers": [],
                "explanation": '"Not only" triggers inversion: auxiliary "does" comes before the subject "pollution", and the main verb changes to infinitive.',
            },
            {
                "question_type": "pick_correct",
                "prompt": "Choose the correct inverted structure:",
                "correct_answer": "Only by investing in education can a country achieve long-term economic growth.",
                "wrong_answers": [
                    "Only by investing in education a country can achieve long-term economic growth.",
                    "Only investing in education can a country achieve long-term economic growth.",
                    "Only by investing in education can achieve a country long-term economic growth.",
                ],
                "explanation": '"Only by [gerund]" triggers inversion: "can a country achieve" (auxiliary before subject).',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "Rarely do governments acknowledge the long-term consequences of their economic policies.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"Rarely" at the start triggers inversion: "do governments acknowledge" is correct.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "Never before ___ the world ___ such rapid technological change.",
                "correct_answer": "has, experienced",
                "wrong_answers": ["did, experience", "the world, experienced", "had, been experienced"],
                "explanation": '"Never before" triggers inversion: "has the world experienced" — present perfect with auxiliary before subject.',
            },
        ],
    },
    {
        "rule_title": "Hedging language for academic caution",
        "rule_text": (
            "Hedging avoids absolute claims and shows academic caution — examiners reward this. "
            "Common hedges: 'It could be argued that...', 'This tends to suggest...', "
            "'X may/might/could contribute to...', 'There appears to be...', "
            "'It is possible/likely/plausible that...', 'To some extent...', "
            "'Evidence suggests that... rather than proves.'"
        ),
        "correct_example": "It could be argued that social media contributes to a decline in face-to-face communication.",
        "incorrect_example": "Social media causes a decline in face-to-face communication.",
        "tip": "Avoid absolute words (always, never, proves, causes) — replace with hedged alternatives (often, tends to, suggests, may contribute to).",
        "sort_order": 8,
        "questions": [
            {
                "question_type": "pick_correct",
                "prompt": "Which sentence demonstrates appropriate hedging?",
                "correct_answer": "Evidence suggests that excessive screen time may have a negative impact on children's development.",
                "wrong_answers": [
                    "Excessive screen time definitely has a negative impact on children's development.",
                    "It is a fact that excessive screen time destroys children's development.",
                    "Everyone knows excessive screen time is bad for children's development.",
                ],
                "explanation": '"Evidence suggests" and "may have" are hedging devices that show academic caution.',
            },
            {
                "question_type": "error_correction",
                "prompt": "Globalisation always leads to cultural erosion in developing countries.",
                "correct_answer": "Globalisation may lead to cultural erosion in developing countries.",
                "wrong_answers": [],
                "explanation": '"Always leads to" is too absolute. Hedging with "may lead to" is more academically appropriate.',
            },
            {
                "question_type": "fill_blank",
                "prompt": "This ___ to ___ that stricter penalties alone are not sufficient to reduce crime.",
                "correct_answer": "tends, suggest",
                "wrong_answers": ["proves, show", "clearly, prove", "definitely, mean"],
                "explanation": '"Tends to suggest" is a hedged expression appropriate for academic writing.',
            },
            {
                "question_type": "correct_or_incorrect",
                "prompt": "It is plausible that increased access to technology could reduce educational inequality to some extent.",
                "correct_answer": "Correct",
                "wrong_answers": [],
                "explanation": '"It is plausible that", "could reduce", and "to some extent" are all appropriate hedging devices.',
            },
        ],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Seed logic
# ═══════════════════════════════════════════════════════════════════════════

ALL_TOPICS = [
    (ARTICLES_TOPIC, ARTICLES_RULES),
    (COMMAS_TOPIC, COMMAS_RULES),
    (CONDITIONALS_TOPIC, CONDITIONALS_RULES),
    (RELATIVE_CLAUSES_TOPIC, RELATIVE_CLAUSES_RULES),
    (HIGH_BAND_TOPIC, HIGH_BAND_RULES),
]


async def seed() -> None:
    pool = get_pool()

    for topic_data, rules_data in ALL_TOPICS:
        existing = await pool.fetchval(
            "SELECT id FROM grammar_topics WHERE user_id IS NULL AND name = $1",
            topic_data["name"],
        )
        if existing:
            logger.info("Topic '%s' already exists (id=%d), skipping", topic_data["name"], existing)
            continue

        topic_id = await pool.fetchval(
            """INSERT INTO grammar_topics (user_id, name, description)
               VALUES (NULL, $1, $2) RETURNING id""",
            topic_data["name"],
            topic_data["description"],
        )
        logger.info("Created topic '%s' (id=%d)", topic_data["name"], topic_id)

        for rule_data in rules_data:
            questions = rule_data.pop("questions", [])
            rule_id = await pool.fetchval(
                """INSERT INTO grammar_rules
                       (user_id, topic_id, rule_title, rule_text,
                        correct_example, incorrect_example, tip, sort_order)
                   VALUES (NULL, $1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                topic_id,
                rule_data["rule_title"],
                rule_data["rule_text"],
                rule_data["correct_example"],
                rule_data["incorrect_example"],
                rule_data["tip"],
                rule_data["sort_order"],
            )

            for q in questions:
                await pool.execute(
                    """INSERT INTO grammar_questions
                           (user_id, rule_id, question_type, prompt,
                            correct_answer, wrong_answers, explanation)
                       VALUES (NULL, $1, $2, $3, $4, $5::jsonb, $6)""",
                    rule_id,
                    q["question_type"],
                    q["prompt"],
                    q["correct_answer"],
                    json.dumps(q["wrong_answers"]),
                    q["explanation"],
                )

            rule_data["questions"] = questions

        logger.info("Seeded %d rules for '%s'", len(rules_data), topic_data["name"])

    logger.info("Grammar seed complete")


async def main() -> None:
    await create_pool()
    try:
        await seed()
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
