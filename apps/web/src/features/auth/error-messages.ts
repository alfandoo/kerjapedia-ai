import type { TranslationKey } from "@/lib/translations";

type Translate = (key: TranslationKey) => string;

/** Maps backend error messages (whose text may be in Indonesian) to a
 * translation key, so the UI can render them in the active app language.
 * If a message is not recognized, the raw message is shown as-is. */
const MESSAGE_TO_KEY: Array<[string, TranslationKey]> = [
  ["Email atau password salah.", "auth.errorWrongCredentials"],
  ["Sesi telah berakhir. Silakan masuk kembali.", "auth.errorSessionExpired"],
  ["Email sudah terdaftar.", "auth.errorEmailExists"],
  ["Kode verifikasi gagal dikirim. Silakan coba lagi.", "auth.otpSendFailed"],
  ["Registrasi gagal. Silakan coba lagi.", "auth.errorRegisterFailed"],
  ["Autentikasi Google gagal. Silakan coba lagi.", "auth.errorGoogle"],
  ["Autentikasi Google gagal.", "auth.errorGoogle"],
  ["Akun Google tidak memiliki email.", "auth.errorGoogleNoEmail"],
  ["Email Google belum terverifikasi.", "auth.errorGoogleUnverified"],
  ["Kode verifikasi salah atau telah kedaluwarsa.", "auth.otpInvalid"],
  ["Kode verifikasi telah kedaluwarsa. Silakan kirim ulang.", "auth.otpExpired"],
  ["Kode verifikasi salah.", "auth.otpInvalid"],
  ["Terlalu banyak percobaan. Silakan kirim ulang kode.", "auth.otpTooMany"],
  ["Sesi pendaftaran tidak valid. Silakan daftar ulang.", "auth.otpInvalidSession"],
  ["Akun berhasil dibuat, namun sesi belum dapat dibuat.", "auth.errorSessionCreate"],
  ["Belum ada pendaftaran untuk email ini.", "auth.errorNoPending"],
  ["Kode verifikasi belum dapat dikirim ulang. Silakan coba lagi.", "auth.otpResendFailed"],
  ["Akun belum dapat dihapus. Silakan coba lagi.", "profile.deleteError"],
  ["Profil belum dapat disimpan.", "profile.error"],
];

/** Lowercase/exact variant used for fuzzy matching when the backend prefix
 * (e.g. "Pendaftaran gagal: …") is attached by an older client path. */
export function translateAuthError(
  translate: Translate,
  rawMessage: string
): string {
  const clean = rawMessage.trim();
  for (const [message, key] of MESSAGE_TO_KEY) {
    if (clean === message || clean.endsWith(message)) {
      return translate(key);
    }
  }
  return clean;
}
