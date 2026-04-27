// Match the format Pydantic's ``EmailStr`` accepts so the frontend
// surfaces the same complaint the backend would, before the round-trip.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(value: string): boolean {
  return EMAIL_RE.test(value);
}
