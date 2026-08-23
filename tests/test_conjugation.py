import unittest

from french_learning.conjugation import conjugation_insights


class ConjugationInsightTest(unittest.TestCase):
    def test_explicit_infinitives_build_ranked_tables_for_observed_tenses(self):
        mistakes = [
            {
                "prompt": "Il faut que tu ___ attention. (faire)",
                "answer": "fasses",
                "user_answer": "fait",
                "grammar_key": "subjonctif",
            },
            {
                "prompt": "Nous ___ au cinéma hier. (aller)",
                "answer": "sommes allés",
                "user_answer": "avons allé",
                "grammar_key": "passe-compose",
            },
            {
                "prompt": "Il faut que tu ___ attention. (faire)",
                "answer": "fasses",
                "user_answer": "fais",
                "grammar_key": "subjonctif",
            },
        ]

        insights = conjugation_insights(mistakes)

        self.assertEqual(["faire", "aller"], [item["verb"] for item in insights])
        self.assertEqual(2, insights[0]["mistake_count"])
        self.assertEqual("fasses", insights[0]["tenses"][0]["forms"]["tu"])
        self.assertEqual("sommes allé(e)s", insights[1]["tenses"][0]["forms"]["nous"])

    def test_answer_form_can_identify_a_verb_without_a_prompt_cue(self):
        insights = conjugation_insights(
            [{
                "prompt": "Si j'avais le temps, je ___ ce cours.",
                "answer": "suivrais",
                "user_answer": "suivrai",
                "grammar_key": "conditionnel",
            }]
        )

        self.assertEqual("suivre", insights[0]["verb"])
        self.assertEqual("Conditionnel présent", insights[0]["tenses"][0]["name"])

    def test_unrecognized_content_is_not_presented_as_a_weak_verb(self):
        insights = conjugation_insights(
            [{
                "prompt": "Voici la personne ___ je parle.",
                "answer": "dont",
                "user_answer": "que",
                "grammar_key": "pronoms-relatifs",
            }]
        )

        self.assertEqual([], insights)


if __name__ == "__main__":
    unittest.main()
