"use client";

import { useState } from "react";
import { LoaderCircle, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldGroup, FieldLabel, FieldDescription } from "@/components/ui/field";
import { useSettings } from "@/features/settings";
import { deleteAccount, updateProfile } from "../api";
import type { UserSession } from "../types";

type Props = { user: UserSession["user"]; onClose: () => void; onReturnFocus: () => void };
export function ProfileModal({ user, onClose, onReturnFocus }: Props) {
  const { t } = useSettings();
  const [name, setName] = useState(user.name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const trimmed = name.trim();
  const valid = trimmed.length > 0 && trimmed.length <= 80;
  const changed = trimmed !== user.name.trim();
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid || !changed || saving) return;
    setSaving(true);
    setError(null);
    try {
      await updateProfile(trimmed);
      toast.success(t("profile.saved"));
      onClose();
    } catch {
      setError(t("profile.error"));
    } finally {
      setSaving(false);
    }
  }
  async function removeAccount() {
    if (!confirmingDelete || deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAccount();
      toast.success(t("profile.deleted"));
      onClose();
    } catch {
      setDeleteError(t("profile.deleteError"));
    } finally {
      setDeleting(false);
    }
  }
  const busy = saving || deleting;
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <DialogContent
        className="w-[calc(100vw_-_2rem)] max-h-[min(660px,calc(100svh_-_40px))] overflow-y-auto sm:max-w-[440px] [scrollbar-width:thin]"
        showCloseButton={!busy}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          onReturnFocus();
        }}
      >
        <DialogHeader>
          <DialogTitle>{t("profile.title")}</DialogTitle>
          <DialogDescription>{t("profile.description")}</DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-4 rounded-xl border border-border p-4">
          <span
            aria-hidden="true"
            className="grid size-14 shrink-0 place-items-center rounded-full bg-javanese text-lg font-bold text-white"
          >
            {user.name.slice(0, 2).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-semibold leading-tight text-foreground">
              {user.name}
            </p>
            <p className="mt-1 truncate text-xs text-muted-foreground">{user.email}</p>
          </div>
          {user.roles.length > 0 ? (
            <span className="shrink-0 rounded-full border border-border bg-muted px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {user.roles[0]}
            </span>
          ) : null}
        </div>

        <form className="flex flex-col gap-5 pt-2" onSubmit={save} aria-busy={saving}>
          <FieldGroup>
            <Field data-invalid={!valid || undefined}>
              <FieldLabel htmlFor="profile-name">{t("profile.name")}</FieldLabel>
              <Input
                id="profile-name"
                className="min-h-11"
                name="name"
                autoComplete="name"
                maxLength={80}
                required
                value={name}
                disabled={saving}
                aria-invalid={!valid}
                aria-describedby={!valid ? "profile-name-error" : undefined}
                onChange={(event) => {
                  setName(event.target.value);
                  setError(null);
                }}
              />
              {!valid ? (
                <FieldDescription id="profile-name-error" className="text-destructive">
                  {t("profile.invalid")}
                </FieldDescription>
              ) : null}
            </Field>
            <Field>
              <FieldLabel htmlFor="profile-email">{t("profile.email")}</FieldLabel>
              <Input
                id="profile-email"
                className="min-h-11 cursor-not-allowed bg-muted/40 text-muted-foreground"
                type="email"
                value={user.email}
                readOnly
                tabIndex={-1}
                aria-readonly="true"
                aria-describedby="profile-email-hint"
              />
              <FieldDescription id="profile-email-hint">{t("profile.emailHint")}</FieldDescription>
            </Field>
          </FieldGroup>

          {error ? (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-[12px] leading-[1.5] text-destructive"
            >
              <TriangleAlert className="mt-[1px] size-4 shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </p>
          ) : null}

          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
              {t("profile.cancel")}
            </Button>
            <Button type="submit" disabled={!valid || !changed || busy}>
              {saving ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
              {saving ? t("profile.saving") : t("profile.save")}
            </Button>
          </div>
        </form>

        <div className="mt-6 rounded-xl border border-destructive/30 bg-destructive/5 p-4">
          <div className="flex items-center gap-2">
            <TriangleAlert className="size-4 shrink-0 text-destructive" aria-hidden="true" />
            <p className="text-sm font-semibold text-foreground">{t("profile.dangerTitle")}</p>
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
            {t("profile.dangerDescription")}
          </p>
          {deleteError ? (
            <p
              role="alert"
              className="mt-3 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] leading-[1.5] text-destructive"
            >
              <TriangleAlert className="mt-[1px] size-4 shrink-0" aria-hidden="true" />
              <span>{deleteError}</span>
            </p>
          ) : null}
          {!confirmingDelete ? (
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setDeleteError(null);
                setConfirmingDelete(true);
              }}
              className="mt-4 border-destructive/50 text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              {t("profile.delete")}
            </Button>
          ) : (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => {
                  setDeleteError(null);
                  setConfirmingDelete(false);
                }}
              >
                {t("profile.deleteCancel")}
              </Button>
              <Button
                type="button"
                variant="destructive"
                disabled={busy}
                onClick={removeAccount}
              >
                {deleting ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
                {deleting ? t("profile.deleting") : t("profile.deleteConfirm")}
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
