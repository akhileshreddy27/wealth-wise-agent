"""Risk profiling: risk *tolerance* (what you are comfortable with, from a questionnaire)
combined with risk *capacity* (what you can afford: age, horizon, dependents, emergency cushion)
into a score from 1 to 10. Capacity caps tolerance."""

QUESTIONNAIRE = [
    {
        "id": "market_drop",
        "question": "Your investments fall 20% in a month. What do you do?",
        "options": ["Sell everything to stop the losses", "Sell some to reduce risk",
                    "Hold and wait for recovery", "Invest more while prices are low"],
    },
    {
        "id": "primary_goal",
        "question": "What matters most to you when investing?",
        "options": ["Protecting my capital", "Steady income with low risk", "Balanced growth",
                    "Maximum long-term growth"],
    },
    {
        "id": "experience",
        "question": "How experienced are you with stocks or mutual funds?",
        "options": ["Never invested", "Only FDs / savings accounts", "Some mutual funds or SIPs",
                    "Regularly invest in stocks"],
    },
    {
        "id": "return_vs_risk",
        "question": "Which portfolio would you pick for one year?",
        "options": ["Best +7%, worst +5%", "Best +12%, worst 0%", "Best +20%, worst -8%", "Best +35%, worst -20%"],
    },
    {
        "id": "income_stability",
        "question": "How stable is your income?",
        "options": ["Very uncertain", "Somewhat uncertain", "Stable", "Very stable with growth"],
    },
]
QUESTION_IDS = {q["id"] for q in QUESTIONNAIRE}


def validate_answers(answers: dict[str, int]) -> None:
    """Every question answered, with an option number from 1 to 4."""
    missing = QUESTION_IDS - answers.keys()
    if missing:
        raise ValueError(f"Missing answers for: {', '.join(sorted(missing))}")
    for qid, value in answers.items():
        if qid not in QUESTION_IDS:
            raise ValueError(f"Unknown question: {qid}")
        if value not in (1, 2, 3, 4):
            raise ValueError(f"Answer for {qid} must be 1-4")


def capacity_score(age: int, horizon_years: int, dependents: int, emergency_months: float) -> float:
    """0..1: how much risk the user can afford to take."""
    age_pts = 1.0 if age < 30 else 0.75 if age < 40 else 0.5 if age < 50 else 0.25 if age < 60 else 0.1
    horizon_pts = 1.0 if horizon_years >= 10 else 0.75 if horizon_years >= 5 else 0.4 if horizon_years >= 3 else 0.1
    dependents_pts = 1.0 if dependents == 0 else 0.7 if dependents <= 2 else 0.4
    cushion_pts = 1.0 if emergency_months >= 6 else 0.6 if emergency_months >= 3 else 0.3
    return 0.35 * age_pts + 0.35 * horizon_pts + 0.15 * dependents_pts + 0.15 * cushion_pts


def compute_risk(answers: dict[str, int], age: int, horizon_years: int, dependents: int,
                 monthly_expenses: float, current_savings: float) -> tuple[int, str]:
    """Return (score 1-10, "conservative" | "moderate" | "aggressive")."""
    validate_answers(answers)
    tolerance = (sum(answers.values()) - len(answers)) / (3 * len(answers))  # 0..1
    emergency_months = current_savings / monthly_expenses if monthly_expenses > 0 else 12
    capacity = capacity_score(age, horizon_years, dependents, emergency_months)

    # A 58-year-old with a 2-year horizon can't be "aggressive", however bold their answers are.
    combined = min(0.6 * tolerance + 0.4 * capacity, capacity + 0.2)
    score = max(1, min(10, round(1 + combined * 9)))
    category = "conservative" if score <= 3 else "moderate" if score <= 6 else "aggressive"
    return score, category
