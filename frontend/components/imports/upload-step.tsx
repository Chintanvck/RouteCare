"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { ImportUploadResponse } from "@/types/import";

interface UploadStepProps {
  onUploaded: (result: ImportUploadResponse) => void;
}

export function UploadStep({ onUploaded }: UploadStepProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setError(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await apiFetch<ImportUploadResponse>("/imports/patients", {
        method: "POST",
        body: formData,
      });
      onUploaded(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload this file. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload Excel File</CardTitle>
        <CardDescription>Upload a TheraOffice patient export (.xlsx or .xls) to get started.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <div
          className={`flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-12 text-center transition-colors ${
            dragOver ? "border-primary bg-primary/5" : "border-input"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const file = e.dataTransfer.files?.[0];
            if (file) handleFile(file);
          }}
        >
          <p className="text-sm text-muted-foreground">Drag an Excel file here, or</p>
          <Button type="button" onClick={() => inputRef.current?.click()} disabled={uploading}>
            {uploading ? "Uploading..." : "Choose File"}
          </Button>
          <p className="text-xs text-muted-foreground">Supported: .xlsx, .xls</p>
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
          />
        </div>
      </CardContent>
    </Card>
  );
}
