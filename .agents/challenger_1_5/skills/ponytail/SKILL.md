# Ponytail Skill Copy
See /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/skills/ponytail/SKILL.md
Core methodology: Minimalist engineering, stdlib/native first, elimination of over-engineering, zero speculative complexity.
Shortest diff wins.
Ladder:
1. Does this need to exist at all? (YAGNI)
2. Already in codebase?
3. Stdlib does it?
4. Native platform feature covers it?
5. Already-installed dependency solves it?
6. Can it be one line?
7. Only then: minimum code that works.
Never simplify away security or input validation.
Non-trivial logic leaves ONE runnable check behind.
