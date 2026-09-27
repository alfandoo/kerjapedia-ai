"use client";

import { useState } from "react";
import type { WorkProfile } from "../types";
import { useSettings } from "@/features/settings";

const PROVINCES = [
  "Aceh", "Sumatera Utara", "Sumatera Barat", "Riau", "Kepulauan Riau",
  "Jambi", "Sumatera Selatan", "Bangka Belitung", "Bengkulu", "Lampung",
  "Banten", "DKI Jakarta", "Jawa Barat", "Jawa Tengah", "DI Yogyakarta",
  "Jawa Timur", "Bali", "Nusa Tenggara Barat", "Nusa Tenggara Timur",
  "Kalimantan Barat", "Kalimantan Tengah", "Kalimantan Selatan",
  "Kalimantan Timur", "Kalimantan Utara", "Sulawesi Utara", "Gorontalo",
  "Sulawesi Tengah", "Sulawesi Barat", "Sulawesi Selatan",
  "Sulawesi Tenggara", "Maluku", "Maluku Utara", "Papua Barat",
  "Papua Barat Daya", "Papua", "Papua Tengah", "Papua Pegunungan",
  "Papua Selatan",
];

type Props = {
  enabled: boolean;
  profile: WorkProfile | null;
  busy: boolean;
  error: string | null;
  onToggle: (enabled: boolean) => void;
  onSave: (profile: WorkProfile) => Promise<void>;
  onDelete: () => Promise<void>;
};

export function PersonalizedControls({
  enabled, profile, busy, error, onToggle, onSave, onDelete,
}: Props) {
  const { t } = useSettings();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<WorkProfile>({
    province: null, employment_status: null, start_date: null, monthly_wage: null,
  });

  const facts = [
    profile?.province,
    profile?.employment_status,
    profile?.start_date && `${t("chat.personalized.start")} ${profile.start_date}`,
    profile?.monthly_wage != null &&
      `${t("chat.personalized.wageShort")} Rp${new Intl.NumberFormat("id-ID").format(profile.monthly_wage)}`,
  ].filter(Boolean).join(" · ");

  return (
    <section className="mb-3 rounded-xl border border-[#b7d3c0] bg-white p-3 text-sm text-[#31523d] dark:border-white/20 dark:bg-[#17291e] dark:text-[#d9f0df]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex cursor-pointer items-center gap-2 font-semibold">
          <input
            type="checkbox"
            checked={enabled}
            disabled={busy}
            onChange={(event) => onToggle(event.target.checked)}
            className="size-4 accent-[#176b3a]"
          />
          {t("chat.personalized.label")}
        </label>
        <button type="button" onClick={() => { setDraft(profile ?? { province: null, employment_status: null, start_date: null, monthly_wage: null }); setEditing((value) => !value); }}
          className="rounded-md px-2 py-1 underline underline-offset-2 focus-visible:outline-2">
          {editing ? t("chat.personalized.close") : t("chat.personalized.edit")}
        </button>
      </div>
      {enabled && <p className="mt-2 text-xs">{facts || t("chat.personalized.empty")}</p>}
      {error && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}
      {editing && (
        <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={(event) => {
          event.preventDefault();
          void onSave(draft).then(() => setEditing(false)).catch(() => {});
        }}>
          <label className="grid gap-1">{t("chat.personalized.province")}
            <select value={draft.province ?? ""} onChange={(event) =>
              setDraft({ ...draft, province: event.target.value || null })}
              className="min-h-11 rounded-md border border-current bg-transparent px-2">
              <option value="">{t("chat.personalized.blank")}</option>
              {PROVINCES.map((province) => <option key={province} value={province}>{province}</option>)}
            </select>
          </label>
          <label className="grid gap-1">{t("chat.personalized.status")}
            <select value={draft.employment_status ?? ""} onChange={(event) =>
              setDraft({ ...draft, employment_status: (event.target.value || null) as WorkProfile["employment_status"] })}
              className="min-h-11 rounded-md border border-current bg-transparent px-2">
              <option value="">{t("chat.personalized.blank")}</option>
              <option value="PKWT">PKWT</option>
              <option value="PKWTT">PKWTT</option>
            </select>
          </label>
          <label className="grid gap-1">{t("chat.personalized.startDate")}
            <input type="date" value={draft.start_date ?? ""} onChange={(event) =>
              setDraft({ ...draft, start_date: event.target.value || null })}
              className="min-h-11 rounded-md border border-current bg-transparent px-2" />
          </label>
          <label className="grid gap-1">{t("chat.personalized.wage")}
            <input type="number" min="0" max="2000000000" value={draft.monthly_wage ?? ""}
              onChange={(event) => setDraft({
                ...draft, monthly_wage: event.target.value === "" ? null : Number(event.target.value),
              })}
              className="min-h-11 rounded-md border border-current bg-transparent px-2" />
          </label>
          <div className="flex gap-3 sm:col-span-2">
            <button type="submit" disabled={busy} className="min-h-11 rounded-md bg-[#176b3a] px-4 text-white disabled:opacity-50">{t("chat.personalized.save")}</button>
            <button type="button" disabled={busy} onClick={() => void onDelete().then(() => setEditing(false)).catch(() => {})}
              className="min-h-11 rounded-md border border-current px-4 disabled:opacity-50">{t("chat.personalized.delete")}</button>
          </div>
        </form>
      )}
    </section>
  );
}
