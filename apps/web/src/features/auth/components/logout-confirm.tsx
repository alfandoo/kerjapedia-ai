"use client";

import { LoaderCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

type LogoutConfirmProps = {
  open: boolean;
  confirming: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
};

export function LogoutConfirmDialog({
  open,
  confirming,
  error,
  onCancel,
  onConfirm,
}: LogoutConfirmProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !confirming) onCancel();
      }}
    >
      <DialogContent className="w-[calc(100vw_-_2rem)] sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Keluar dari akun?</DialogTitle>
          <DialogDescription>
            Sesi Anda akan diakhiri di perangkat ini. Anda perlu masuk kembali untuk
            melanjutkan.
          </DialogDescription>
        </DialogHeader>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={confirming}>
            Batal
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={confirming}>
            {confirming ? (
              <>
                <LoaderCircle aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />
                Keluar...
              </>
            ) : (
              "Ya, keluar"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
