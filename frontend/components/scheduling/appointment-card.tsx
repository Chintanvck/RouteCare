import { Badge } from "@/components/ui/badge";
import type { Appointment } from "@/types/appointment";

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  SCHEDULED: "default",
  COMPLETED: "secondary",
  CANCELLED: "outline",
  NO_SHOW: "destructive",
};

export function AppointmentCard({
  appointment,
  onClick,
  showTherapist,
}: {
  appointment: Appointment;
  onClick: () => void;
  showTherapist?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-md border p-3 text-left text-sm transition hover:border-primary hover:bg-accent ${
        appointment.status === "CANCELLED" ? "opacity-60" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">
          {appointment.start_time.slice(0, 5)}–{appointment.end_time.slice(0, 5)}
        </span>
        <Badge variant={STATUS_VARIANT[appointment.status] ?? "default"}>{appointment.status}</Badge>
      </div>
      <p className="mt-1">{appointment.patient_name}</p>
      {showTherapist && <p className="text-muted-foreground">{appointment.therapist_name}</p>}
    </button>
  );
}
