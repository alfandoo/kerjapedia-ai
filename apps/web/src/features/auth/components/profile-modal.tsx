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
        className="w-[calc(100vw_-_2rem)] sm:max-w-[440px]"
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
        <div className="flex items-center gap-3 pb-1 pt-2">
          <span
            aria-hidden="true"
            className="grid size-14 shrink-0 place-items-center rounded-full bg-accent text-lg font-semibold text-accent-foreground"
          >
            {user.name.slice(0, 2).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium leading-tight">{user.name}</p>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">{user.email}</p>
          </div>
        </div>
        <form className="flex flex-col gap-5" onSubmit={save} aria-busy={saving}>
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
                <FieldDescription id="profile-name-error">{t("profile.invalid")}</FieldDescription>
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
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
              {t("profile.cancel")}
            </Button>
            <Button type="submit" disabled={!valid || !changed || busy}>
              {saving ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
              {saving ? t("profile.saving") : t("profile.save")}
            </Button>
          </div>
        </form>
        <div className="mt-4 rounded-xl border border-destructive/40 bg-destructive/5 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-destructive">
            <TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
            {t("profile.dangerTitle")}
          </p>
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
            {t("profile.dangerDescription")}
          </p>
          {deleteError ? (
            <p role="alert" className="mt-2 text-sm text-destructive">
              {deleteError}
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
              className="mt-3 border-destructive/50 text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              {t("profile.delete")}
            </Button>
          ) : (
            <div className="mt-3 flex flex-wrap gap-2">
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
