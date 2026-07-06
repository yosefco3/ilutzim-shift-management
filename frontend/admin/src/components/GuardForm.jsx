import { useState, useEffect, useRef } from 'react';
import messages, { ROLE_OPTIONS, PREFERRED_SHIFT_OPTIONS } from '../utils/messages';

// Stage 3 (payroll): the payroll employee-id field rides the guard form only
// when the attendance feature is compiled in. (The YLM code stays backend-only —
// the column exists for the report header but is not exposed in the form.)
const ATTENDANCE_ENABLED = import.meta.env.VITE_ATTENDANCE_ENABLED !== 'false';

export default function GuardForm({ guard, onSave, onCancel }) {
  const formRef = useRef(null);
  const [form, setForm] = useState({
    first_name: guard?.first_name || '',
    last_name: guard?.last_name || '',
    phone_number: guard?.phone_number || '',
    roles: guard?.roles || [],
    preferred_shift: guard?.preferred_shift || '',
    payroll_employee_id: guard?.payroll_employee_id || '',
  });

  useEffect(() => {
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const toggleRole = (value) => {
    setForm((prev) => ({
      ...prev,
      roles: prev.roles.includes(value)
        ? prev.roles.filter((r) => r !== value)
        : [...prev.roles, value],
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(form);
  };

  return (
    <form ref={formRef} className="card" onSubmit={handleSubmit}>
      <h3>{guard ? messages.guards.editTitle : messages.guards.addTitle}</h3>
      <div className="form-group">
        <label>{messages.guards.firstName}</label>
        <input name="first_name" value={form.first_name} onChange={handleChange} required />
      </div>
      <div className="form-group">
        <label>{messages.guards.lastName}</label>
        <input name="last_name" value={form.last_name} onChange={handleChange} required />
      </div>
      <div className="form-group">
        <label>{messages.guards.phone}</label>
         <input name="phone_number" value={form.phone_number} onChange={handleChange} required />
      </div>
      <div className="form-group">
        <label>{messages.guards.preferredShift}</label>
        <select name="preferred_shift" value={form.preferred_shift} onChange={handleChange}>
          {PREFERRED_SHIFT_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>
      {ATTENDANCE_ENABLED && (
        <div className="form-group">
          <label>{messages.guards.payrollEmployeeId}</label>
          <input
            name="payroll_employee_id"
            value={form.payroll_employee_id}
            onChange={handleChange}
            placeholder={messages.guards.payrollOptional}
          />
        </div>
      )}
      <div className="form-group">
        <label>{messages.guards.role}</label>
        <div className="requirement-checks">
          {ROLE_OPTIONS.map((r) => (
            <label key={r.value} className="requirement-check">
              <input
                type="checkbox"
                aria-label={r.label}
                checked={form.roles.includes(r.value)}
                onChange={() => toggleRole(r.value)}
              />
              {r.label}
            </label>
          ))}
        </div>
      </div>
      <div className="form-actions">
        <button type="submit" className="btn btn-primary">{messages.common.save}</button>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>{messages.common.cancel}</button>
      </div>
    </form>
  );
}