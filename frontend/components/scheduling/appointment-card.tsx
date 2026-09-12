import { Badge } from "@/components/ui/badge";
import { buildNavigationUrl } from "@/lib/navigation";
import type { Appointment } from "@/types/appointment";

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  SCHEDULED: "default",
  COMPLETED: "secondary",
  CANCELLED: "outline",
  NO_SHOW: "destructive",
};

/** Stops a click on the "Navigate" button from also triggering the card's own onClick (opening
 * the edit dialog) - the two actions shouldn't fight each other. */
function handleNavigateClick(event: React.MouseEvent, url: string | null) {
  event.stopPropagation();
  if (url) window.open(url, "_blank", "noopener,noreferrer");
}

export function AppointmentCard({
  appointment,
  onClick,
  showTherapist,
  travelTimeMinutes,
}: {
  appointment: Appointment;
  onClick: () => void;
  showTherapist?: boolean;
  /** Estimated driving time to reach this appointment from the previous stop - omitted (not
   * computed) on pages that don't already have a same-day ordered route, e.g. the plain
   * schedule grid; the therapist dashboard's "Today" panel supplies it. */
  travelTimeMinutes?: number | null;
}) {
  const navigationUrl = buildNavigationUrl({
    latitude: appointment.patient_latitude,
    longitude: appointment.patient_longitude,
    address: appointment.patient_address,
  });

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}
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
      <p className="mt-1 font-medium">{appointment.patient_name}</p>
      {showTherapist && <p className="text-muted-foreground">{appointment.therapist_name}</p>}
      <p className="mt-0.5 truncate text-xs text-muted-foreground">{appointment.patient_address}</p>
      {travelTimeMinutes != null && (
        <p className="mt-0.5 text-xs text-muted-foreground">~{Math.round(travelTimeMinutes)} min drive</p>
      )}
      {navigationUrl && (
        <button
          type="button"
          onClick={(e) => handleNavigateClick(e, navigationUrl)}
          className="mt-2 inline-flex h-8 items-center gap-1 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        >
          Navigate
        </button>
      )}
    </div>
  );
}
