import re

with open("docs/requirements.md", "r", encoding="utf-8") as f:
    content = f.read()

# Update shift count text
content = content.replace(
    '勤務パターンは、早1, 早2, 日1, 日2, 遅1, 遅2, 夜1, 夜2, 1〜8, 休, 明 (全18パターン)',
    '勤務パターンは、早1, 早2, 日1, 日2, 遅1, 遅2, 夜1, 夜2, 1〜8, 休, 明, 通8, 通9, 有 (全21パターン)'
)

# Add 通院介助 to the bullet points
content = content.replace(
    '- `パート4`: 1, 2, 3, 4, 5, 6, 7, 8, 休, 明　が勤務可能\n',
    '- `パート4`: 1, 2, 3, 4, 5, 6, 7, 8, 休, 明　が勤務可能\n        - `通院介助`: 通8, 通9, 休, 有　が勤務可能\n'
)

# Add to the table
table_addition = """| 18 | 8 | 13:00 | 19:00 | パート4専用パターン |
| 19 | 通8 | 08:00 | 09:00 | 通院介助専用パターン |
| 20 | 通9 | 09:00 | 10:00 | 通院介助専用パターン |
| 21 | 有 | 00:00 | 00:00 | 有給休暇 |"""
content = content.replace('| 18 | 8 | 13:00 | 19:00 | パート4専用パターン |', table_addition)

with open("docs/requirements.md", "w", encoding="utf-8") as f:
    f.write(content)
