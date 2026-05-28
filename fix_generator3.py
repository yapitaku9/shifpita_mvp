with open("app/services/generator.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

out = []
skip = False
for line in lines:
    if 'if emp["employment_type"] == EmploymentType.HOSPITAL_VISIT_SUPPORT:' in line:
        skip = True
        out.append(line)
        out.append('                # 2. 通院日のシフトを制御する\n')
        out.append('                for d_str in date_strs:\n')
        out.append('                    day_special_infos = special_days_map.get(d_str, [])\n')
        out.append('                    is_hospital_day_8 = any(sdi.visit_time == "08:00" for sdi in day_special_infos)\n')
        out.append('                    is_hospital_day_9 = any(sdi.visit_time == "09:00" for sdi in day_special_infos)\n')
        out.append('\n')
        out.append('                    if not is_hospital_day_8 and "通8" in self.SHIFTS_WORK:\n')
        out.append('                        prob += x[emp_id, d_str, "通8"] == 0, f"NoHospital8_{emp_id}_{d_str}"\n')
        out.append('                    if not is_hospital_day_9 and "通9" in self.SHIFTS_WORK:\n')
        out.append('                        prob += x[emp_id, d_str, "通9"] == 0, f"NoHospital9_{emp_id}_{d_str}"\n')
        out.append('\n')
        out.append('                # この従業員は、HOSPITAL_SHIFTS 以外の全ての SHIFTS_WORK には入れない\n')
        out.append('                other_work_shifts = [s for s in self.SHIFTS_WORK if s not in HOSPITAL_SHIFTS]\n')
        out.append('                if other_work_shifts:\n')
        out.append('                    for d_str in date_strs:\n')
        out.append('                        prob += (\n')
        out.append('                            pulp.lpSum(x[emp_id, d_str, s] for s in other_work_shifts) == 0,\n')
        out.append('                            f"HospitalSupport_GeneralForbidden_{emp_id}_{d_str}",\n')
        out.append('                        )\n')
        continue
    
    if skip and 'f"HospitalSupport_GeneralForbidden_{emp_id}_{d_str}",' in line:
        # read the next line to close the parens
        skip_lines_rem = 1
        continue
    
    if skip:
        try:
            if skip_lines_rem > 0:
                skip_lines_rem -= 1
                if skip_lines_rem == 0:
                    skip = False
                continue
        except NameError:
            pass
        continue

    out.append(line)

with open("app/services/generator.py", "w", encoding="utf-8") as f:
    f.writelines(out)
