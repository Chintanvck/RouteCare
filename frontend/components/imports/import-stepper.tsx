import { cn } from "@/lib/utils";

const STEPS = ["Upload", "Column Mapping", "Validation & Duplicates", "Preview & Confirm", "Results"];

export function ImportStepper({ currentStep }: { currentStep: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-2 text-sm">
      {STEPS.map((label, index) => {
        const stepNumber = index + 1;
        const isActive = stepNumber === currentStep;
        const isDone = stepNumber < currentStep;
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium",
                isActive && "bg-primary text-primary-foreground",
                isDone && "bg-primary/20 text-primary",
                !isActive && !isDone && "bg-muted text-muted-foreground"
              )}
            >
              {stepNumber}
            </span>
            <span className={cn(isActive ? "font-medium text-foreground" : "text-muted-foreground")}>{label}</span>
            {stepNumber !== STEPS.length && <span className="mx-1 text-muted-foreground">&rarr;</span>}
          </li>
        );
      })}
    </ol>
  );
}
