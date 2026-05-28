import re

with open("app/services/generator.py", "r", encoding="utf-8") as f:
    content = f.read()

# Restore HOSPITAL_SHIFTS
content = re.sub(r'HOSPITAL_SHIFTS\s*=\s*\[\]', 'HOSPITAL_SHIFTS = ["通8", "通9"]', content)

with open("app/services/generator.py", "w", encoding="utf-8") as f:
    f.write(content)
