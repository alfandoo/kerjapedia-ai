export type PasswordPolicyIssue =
  | "min_length"
  | "max_length"
  | "common"
  | "repeated_character"
  | "includes_email"
  | "character_classes";

export type PasswordStrength = "weak" | "fair" | "strong";

export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 64;

const EMAIL_PATTERN =
  /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/;

const TYPO_DOMAINS = new Set([
  // gmail
  "gmial.com", "gmial.co", "gmial.id", "gamil.com", "gamil.co", "gmail.co",
  "gmail.ocm", "gmail.cmo", "gmailcom.com", "gmaill.com", "gmai.com",
  "gmaill.co", "gmale.com", "gmali.com", "gmiall.com", "gmail.con",
  "gmail.c.om", "gmaill.net", "gmaill.org", "gmail1.com",
  "gmiall.co", "gmails.com", "gmailss.com", "gmil.com", "gmeil.com",
  "geemail.com", "gmial.net", "gamil.net", "gmailcon",
  "gmiall.com.co",
  // yahoo
  "ahoo.com", "yhhhoo.com", "yahho.com", "yahooo.com", "yahoo.cm",
  "yahoo.co", "yhooo.com", "yahoo.con", "yahhoo.com", "yahuu.com",
  "yaho.com", "yhoo.com",
  // hotmail / outlook
  "hotmal.com", "hotmil.com", "hotmial.com", "hotmail.cm", "hotmail.co",
  "hotmaill.com", "hotmail.con", "hotmial.co", "oeutlook.com",
  "outlok.com", "outloo.com", "outloook.com", "outllook.com", "outllok.com",
  "outlokk.com", "outook.com", "outllook.co", "outlook.co", "outlok.co",
  // proton / icloud / others
  "protonmal.com", "protonmial.com", "pmail.com", "iclod.com", "icloud.co",
  "iclod.co", "icloud.cm", "icloud.com.co", "icloudd.com", "icloudid.com",
]);

const KNOWN_PROVIDER_DOMAINS: Record<string, Set<string>> = {
  gmail: new Set(["gmail.com"]),
  yahoo: new Set(["yahoo.com", "yahoo.co.id", "yahoo.co.uk", "yahoo.ca", "yahoo.co.in"]),
  outlook: new Set(["outlook.com", "outlook.com.br"]),
  hotmail: new Set(["hotmail.com", "hotmail.de", "hotmail.co.uk", "hotmail.fr"]),
  icloud: new Set(["icloud.com"]),
  me: new Set(["me.com"]),
  mac: new Set(["mac.com"]),
  protonmail: new Set(["protonmail.com"]),
  proton: new Set(["proton.me"]),
  pm: new Set(["pm.me"]),
};

export function isValidEmail(email: string): boolean {
  if (!EMAIL_PATTERN.test(email)) return false;
  const domain = email.split("@").pop()?.toLowerCase() ?? "";
  if (TYPO_DOMAINS.has(domain)) return false;
  const base = domain.split(".")[0];
  const accepted = KNOWN_PROVIDER_DOMAINS[base];
  if (accepted && !accepted.has(domain)) return false;
  return true;
}

const COMMON_PASSWORDS = new Set([
  "password",
  "password1",
  "password123",
  "12345678",
  "123456789",
  "1234567890",
  "qwertyuiop",
  "qwerty123",
  "qwerty",
  "abc12345",
  "abc123",
  "letmein",
  "iloveyou",
  "welcome123",
  "admin123",
  "admin1234",
  "kerjapedia",
  "kerjapedia123",
  "11111111",
  "22222222",
  "00000000",
  "football",
  "dragon",
  "monkey",
  "master",
  "superman",
  "baobab",
  "p@ssw0rd",
  "trustno1",
]);

function characterClassCount(password: string): number {
  let classes = 0;
  if (/[a-z]/.test(password)) classes += 1;
  if (/[A-Z]/.test(password)) classes += 1;
  if (/[0-9]/.test(password)) classes += 1;
  if (/[^a-zA-Z0-9]/.test(password)) classes += 1;
  return classes;
}

function localPart(email: string | undefined): string {
  if (!email) return "";
  const [local = ""] = email.split("@");
  return local.length >= 3 ? local.toLowerCase() : "";
}

export function passwordIssues(
  password: string,
  opts: { email?: string } = {}
): PasswordPolicyIssue[] {
  const issues: PasswordPolicyIssue[] = [];
  if (password.length < PASSWORD_MIN_LENGTH) issues.push("min_length");
  if (password.length > PASSWORD_MAX_LENGTH) issues.push("max_length");
  const normalized = password.toLowerCase();
  if (COMMON_PASSWORDS.has(normalized)) issues.push("common");
  if (/^(.)\1+$/.test(password)) issues.push("repeated_character");
  const local = localPart(opts.email);
  if (local && password.toLowerCase().includes(local)) issues.push("includes_email");
  if (password.length >= 4 && characterClassCount(password) < 3) issues.push("character_classes");
  return issues;
}

export function passwordStrength(
  password: string,
  opts: { email?: string } = {}
): { level: PasswordStrength; issues: PasswordPolicyIssue[] } {
  const issues = passwordIssues(password, opts);
  const blocking = issues.filter(
    (issue) => issue !== "character_classes"
  ).length;
  if (blocking > 0 || password.length < PASSWORD_MIN_LENGTH) return { level: "weak", issues };
  const classes = characterClassCount(password);
  if (password.length >= 12 && classes >= 4) return { level: "strong", issues };
  if (password.length >= 8 && classes >= 3) return { level: "fair", issues };
  return { level: "weak", issues };
}

export function passwordAcceptable(
  password: string,
  opts: { email?: string } = {}
): boolean {
  if (!password) return false;
  const { level, issues } = passwordStrength(password, opts);
  return level !== "weak" && issues.length === 0;
}
