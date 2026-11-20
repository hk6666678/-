import { useState } from "react";
import { tongjiColleges } from "./tongjiColleges";

const colleges = [...tongjiColleges, "合成试用学院"];
const other = "__other_college__";

type Props = {
  label: string;
  name?: string;
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  required?: boolean;
  disabled?: boolean;
};

export function CollegeSelect({
  label, name, value, defaultValue = "", onChange, required, disabled,
}: Props) {
  const [localValue, setLocalValue] = useState(defaultValue);
  const [custom, setCustom] = useState(false);
  const college = value ?? localValue;
  const change = (next: string) => {
    setLocalValue(next);
    onChange?.(next);
  };
  return (
    <div>
      <label>
        {label}
        <select
          aria-label={label}
          name={custom ? undefined : name}
          required={required}
          disabled={disabled}
          value={custom ? other : college}
          onChange={(event) => {
            const next = event.target.value;
            setCustom(next === other);
            change(next === other ? "" : next);
          }}
        >
          <option value="">{required ? "请选择学院" : "请选择学院（可留空）"}</option>
          {colleges.map((item) => <option key={item} value={item}>{item}</option>)}
          {!custom && college && !colleges.includes(college) && <option value={college}>{college}</option>}
          <option value={other}>其他学院（手动填写）</option>
        </select>
      </label>
      {custom && (
        <label>
          其他学院名称
          <input name={name} value={college} disabled={disabled} maxLength={100} required onChange={(event) => change(event.target.value)} />
        </label>
      )}
    </div>
  );
}
