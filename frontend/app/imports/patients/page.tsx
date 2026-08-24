"use client";

import { useCallback, useEffect, useState } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { ImportStepper } from "@/components/imports/import-stepper";
import { MappingStep } from "@/components/imports/mapping-step";
import { PreviewStep } from "@/components/imports/preview-step";
import { ResultsStep } from "@/components/imports/results-step";
import { UploadStep } from "@/components/imports/upload-step";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { apiFetch } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { ImportJob, ImportUploadResponse } from "@/types/import";

type WizardStep = "upload" | "mapping" | "processing" | "preview" | "importing" | "results";

const POLL_INTERVAL_MS = 1500;

export default function ImportPatientsPage() {
  const { checked } = useRequireAuth();

  const [step, setStep] = useState<WizardStep>("upload");
  const [uploadResult, setUploadResult] = useState<ImportUploadResponse | null>(null);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [processingError, setProcessingError] = useState<string | null>(null);

  const pollJob = useCallback(async (importId: string, onDone: (job: ImportJob) => void) => {
    const poll = async () => {
      const latest = await apiFetch<ImportJob>(`/imports/${importId}`);
      if (latest.status === "PROCESSING") {
        setJob(latest);
        setTimeout(poll, POLL_INTERVAL_MS);
      } else {
        onDone(latest);
      }
    };
    poll();
  }, []);

  useEffect(() => {
    if (step !== "processing" || !job) return;
    // Handles the case where confirm-mapping's initial response already
    // finished validating before the first poll (small files, eager
    // Celery in dev) - otherwise pollJob above drives the transition.
    if (job.status === "PENDING" && job.valid_records !== null) {
      setStep("preview");
    } else if (job.status === "FAILED") {
      setProcessingError(job.error_message ?? "Validation failed unexpectedly.");
    }
  }, [step, job]);

  function reset() {
    setStep("upload");
    setUploadResult(null);
    setJob(null);
    setProcessingError(null);
  }

  function handleUploaded(result: ImportUploadResponse) {
    setUploadResult(result);
    setStep("mapping");
  }

  async function handleMappingSubmit(mapping: Record<string, string>) {
    if (!uploadResult) return;
    const updated = await apiFetch<ImportJob>(`/imports/${uploadResult.id}/mapping`, {
      method: "POST",
      body: JSON.stringify({ mapping }),
    });
    setJob(updated);
    setProcessingError(null);

    if (updated.status === "PENDING" && updated.valid_records !== null) {
      setStep("preview");
      return;
    }

    setStep("processing");
    pollJob(uploadResult.id, (finalJob) => {
      setJob(finalJob);
      if (finalJob.status === "FAILED") {
        setProcessingError(finalJob.error_message ?? "Validation failed unexpectedly.");
      } else {
        setStep("preview");
      }
    });
  }

  async function handleConfirm(includeDuplicates: boolean) {
    if (!job) return;
    const updated = await apiFetch<ImportJob>(`/imports/${job.id}/confirm`, {
      method: "POST",
      body: JSON.stringify({ include_duplicates: includeDuplicates }),
    });
    setJob(updated);
    setStep("importing");
    pollJob(job.id, (finalJob) => {
      setJob(finalJob);
      setStep("results");
    });
  }

  if (!checked) return null;

  return (
    <>
      <AppHeader />
      <main className="container max-w-4xl space-y-6 py-8">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">Import Patients</h1>
          <p className="text-sm text-muted-foreground">
            Bring your existing patient list into RouteCare AI from a TheraOffice Excel export.
          </p>
          <ImportStepper currentStep={stepNumber(step)} />
        </div>

        {step === "upload" && <UploadStep onUploaded={handleUploaded} />}

        {step === "mapping" && uploadResult && (
          <MappingStep
            detectedHeaders={uploadResult.detected_headers}
            suggestedMapping={uploadResult.suggested_mapping}
            onSubmit={handleMappingSubmit}
            onCancel={reset}
          />
        )}

        {(step === "processing" || step === "importing") && (
          <Card>
            <CardHeader>
              <CardTitle>{step === "processing" ? "Validating your file..." : "Importing patients..."}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {processingError ? (
                <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {processingError}
                </div>
              ) : (
                <>
                  <Progress
                    value={job && job.total_records ? (job.processed_records / job.total_records) * 100 : 0}
                  />
                  <p className="text-sm text-muted-foreground">
                    {job?.processed_records ?? 0} of {job?.total_records ?? "?"} rows processed
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {step === "preview" && job && (
          <PreviewStep job={job} onConfirm={handleConfirm} onCancel={reset} />
        )}

        {step === "results" && job && <ResultsStep job={job} onStartNew={reset} />}
      </main>
    </>
  );
}

function stepNumber(step: WizardStep): number {
  switch (step) {
    case "upload":
      return 1;
    case "mapping":
      return 2;
    case "processing":
      return 3;
    case "preview":
      return 4;
    case "importing":
    case "results":
      return 5;
    default:
      return 1;
  }
}
