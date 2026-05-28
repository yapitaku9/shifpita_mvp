import re

with open("app/services/generator.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove HOSPITAL_SHIFTS = ["通8", "通9"]
content = re.sub(r'HOSPITAL_SHIFTS\s*=\s*\["通8", "通9"\]', 'HOSPITAL_SHIFTS = []', content)

# 2. Update SHIFTS_PART_TIME_SHORT_WORK + HOSPITAL_SHIFTS if needed
# We can just leave HOSPITAL_SHIFTS = [] so the array additions still work and do nothing!

with open("app/services/generator.py", "w", encoding="utf-8") as f:
    f.write(content)
