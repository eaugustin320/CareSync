# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("caresync-server")

@mcp.tool()
def get_medication_info(medication_name: str) -> str:
    """Get safety information and details about a medication.

    Args:
        medication_name: The name of the medication (e.g. aspirin, ibuprofen, metformin, lisinopril).
    """
    meds = {
        "aspirin": (
            "Aspirin is used to reduce fever, relieve mild to moderate pain, and prevent blood clots. "
            "Common side effect: upset stomach. Standard adult dosage: 81mg to 325mg daily. "
            "Warning: Do not give to children/teenagers due to risk of Reye's syndrome."
        ),
        "ibuprofen": (
            "Ibuprofen is a nonsteroidal anti-inflammatory drug (NSAID) used to reduce pain, fever, and inflammation. "
            "Common side effect: nausea, mild heartburn. Standard adult dosage: 200mg to 400mg every 4 to 6 hours. "
            "Warning: Take with food to avoid stomach irritation."
        ),
        "metformin": (
            "Metformin is an oral medication to control blood sugar levels in people with type 2 diabetes. "
            "Common side effect: diarrhea, nausea. Standard adult dosage: 500mg to 1000mg daily. "
            "Warning: Monitor kidney function periodically."
        ),
        "lisinopril": (
            "Lisinopril is an ACE inhibitor used to treat high blood pressure and heart failure. "
            "Common side effect: dry cough, dizziness. Standard adult dosage: 10mg to 40mg daily. "
            "Warning: Do not take during pregnancy."
        )
    }
    name = medication_name.lower().strip()
    return meds.get(name, f"No detailed medication records found for '{medication_name}'. Please consult your doctor.")

@mcp.tool()
def get_healthy_recipes(dietary_restriction: str) -> str:
    """Get healthy recipe recommendations matching a dietary restriction.

    Args:
        dietary_restriction: The dietary requirement (e.g. low-carb, low-sodium, vegan, gluten-free).
    """
    recipes = {
        "low-carb": (
            "Recipe: Grilled Lemon Herb Chicken with Roasted Broccoli.\n"
            "Ingredients: Chicken breast, lemon, garlic, olive oil, broccoli.\n"
            "Instructions: Grill chicken until internal temp is 165°F. Toss broccoli in olive oil, pinch of salt, and roast at 400°F for 20 mins."
        ),
        "low-sodium": (
            "Recipe: Herb-Crusted Baked Salmon.\n"
            "Ingredients: Salmon fillet, dill, parsley, garlic, olive oil, lemon juice.\n"
            "Instructions: Mix chopped herbs with olive oil/lemon juice and spread over salmon. Bake at 375°F for 12-15 mins."
        ),
        "vegan": (
            "Recipe: Quinoa and Black Bean Salad.\n"
            "Ingredients: Quinoa, black beans, corn, red bell pepper, cilantro, lime vinaigrette.\n"
            "Instructions: Cook quinoa and let cool. Toss with beans, veggies, chopped cilantro, and lime vinaigrette."
        ),
        "gluten-free": (
            "Recipe: Garlic Butter Shrimp with Zucchini Noodles.\n"
            "Ingredients: Shrimp, zucchini spirals, garlic, butter, lemon juice, parsley.\n"
            "Instructions: Saute garlic and shrimp in butter for 3-4 mins. Add lemon juice and toss in zucchini noodles for 2 mins."
        )
    }
    restriction = dietary_restriction.lower().strip()
    return recipes.get(restriction, (
        "Recipe: Healthy Mixed Greens Salad.\n"
        "Ingredients: Leafy greens, cucumbers, cherry tomatoes, olive oil, balsamic vinegar.\n"
        "Instructions: Combine greens and vegetables, drizzle with olive oil and vinegar. (A general healthy choice for '" + dietary_restriction + "')"
    ))

@mcp.tool()
def parse_medical_abbreviations(abbreviation: str) -> str:
    """Translate Latin medical abbreviations and prescription jargon to plain English.

    Args:
        abbreviation: The abbreviation to translate (e.g. qd, bid, tid, qid, prn, hs).
    """
    abbs = {
        "qd": "once daily (from Latin 'quaque die')",
        "bid": "twice a day (from Latin 'bis in die')",
        "tid": "three times a day (from Latin 'ter in die')",
        "qid": "four times a day (from Latin 'quater in die')",
        "prn": "as needed (from Latin 'pro re nata')",
        "hs": "at bedtime (from Latin 'hora somni')",
        "ac": "before meals (from Latin 'ante cibum')",
        "pc": "after meals (from Latin 'post cibum')",
        "po": "by mouth (from Latin 'per os')"
    }
    term = abbreviation.lower().strip().replace(".", "")
    return abbs.get(term, f"The abbreviation '{abbreviation}' is not in the CareSync database. Please refer to standard medical references.")

if __name__ == "__main__":
    mcp.run()
