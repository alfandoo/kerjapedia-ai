"use client";

import { useState } from "react";
import { LoaderCircle } from "lucide-react";
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
import { updateProfile } from "../api";
import type { UserSession } from "../types";

type Props = { user: UserSession["user"]; onClose: () => void; onReturnFocus: () => void };
export function ProfileModal({ user, onClose, onReturnFocus }: Props) {
  const { t } = useSettings();
  const [name, setName] = useState(user.name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose();
      }}
    >
      <DialogContent
        className="w-[calc(100vw_-_2rem)] sm:max-w-[440px]"
        showCloseButton={!saving}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          onReturnFocus();
        }}
      >
        <DialogHeader>
          <DialogTitle>{t("profile.title")}</DialogTitle>
          <DialogDescription>{t("profile.description")}</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-3 py-2">
          <span
            aria-hidden="true"
            className="grid size-14 shrink-0 place-items-center rounded-full bg-accent text-lg font-semibold text-accent-foreground"
          >
            {user.name.slice(0, 2).toUpperCase()}
          </span>
          <p className="min-w-0 truncate font-medium">{user.name}</p>
        </div>
        <form className="flex flex-col gap-6" onSubmit={save} aria-busy={saving}>
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
                className="min-h-11"
                type="email"
                value={user.email}
                readOnly
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
            <Button type="button" variant="outline" disabled={saving} onClick={onClose}>
              {t("profile.cancel")}
            </Button>
            <Button type="submit" disabled={!valid || !changed || saving}>
              {saving ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
              {saving ? t("profile.saving") : t("profile.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
