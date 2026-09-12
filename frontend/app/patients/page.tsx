"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { AppHeader } from "@/components/layout/app-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/lib/use-current-user";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { PaginatedResponse, Patient, SortBy, SortOrder } from "@/types/patient";

const PAGE_SIZE = 25;

export default function PatientsListPage() {
  const { checked } = useRequireAuth();
  const { user: currentUser } = useCurrentUser(checked);
  const isTherapist = currentUser?.role === "THERAPIST";

  const [search, setSearch] = useState("");
  const [zipCode, setZipCode] = useState("");
  const [sortBy, setSortBy] = useState<SortBy>("created_at");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [page, setPage] = useState(1);

  const [data, setData] = useState<PaginatedResponse<Patient> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadPatients = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(PAGE_SIZE),
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      if (search.trim()) params.set("search", search.trim());
      if (zipCode.trim()) params.set("zip_code", zipCode.trim());

      const result = await apiFetch<PaginatedResponse<Patient>>(`/patients?${params.toString()}`);
      setData(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load patients. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [page, search, zipCode, sortBy, sortOrder]);

  useEffect(() => {
    if (checked) loadPatients();
  }, [checked, loadPatients]);

  function handleSearchSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPage(1);
    loadPatients();
  }

  if (!checked) return null;

  return (
    <>
      <AppHeader />
      <main className="container space-y-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Patients</h1>
            <p className="text-sm text-muted-foreground">
              {isTherapist ? "Patients on your schedule." : "Manage your clinic's patient records."}
            </p>
          </div>
          {/* Creating/importing patients is a scheduler/admin action - a THERAPIST only ever
              views their assigned patients (see patient_service._active_patients_query), so these
              buttons would just 403 for them. */}
          {!isTherapist && (
            <div className="flex gap-2">
              <Button variant="outline" asChild>
                <Link href="/imports/patients">Import from Excel</Link>
              </Button>
              <Button asChild>
                <Link href="/patients/new">Add patient</Link>
              </Button>
            </div>
          )}
        </div>

        <form onSubmit={handleSearchSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <label className="text-sm font-medium" htmlFor="search">
              Search by name
            </label>
            <Input
              id="search"
              placeholder="e.g. Mary Smith"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="space-y-1.5 sm:w-40">
            <label className="text-sm font-medium" htmlFor="zip">
              ZIP code
            </label>
            <Input id="zip" placeholder="07030" value={zipCode} onChange={(e) => setZipCode(e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:w-44">
            <label className="text-sm font-medium" htmlFor="sort_by">
              Sort by
            </label>
            <select
              id="sort_by"
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
              value={sortBy}
              onChange={(e) => {
                setSortBy(e.target.value as SortBy);
                setPage(1);
              }}
            >
              <option value="created_at">Date added</option>
              <option value="name">Name</option>
              <option value="zip_code">ZIP code</option>
            </select>
          </div>
          <div className="space-y-1.5 sm:w-36">
            <label className="text-sm font-medium" htmlFor="sort_order">
              Order
            </label>
            <select
              id="sort_order"
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
              value={sortOrder}
              onChange={(e) => {
                setSortOrder(e.target.value as SortOrder);
                setPage(1);
              }}
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </div>
          <Button type="submit" variant="secondary">
            Apply
          </Button>
        </form>

        {loading && (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        )}

        {!loading && error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {!loading && !error && data && data.items.length === 0 && (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed py-16 text-center">
            <p className="text-sm text-muted-foreground">
              {search || zipCode
                ? "No patients match your search."
                : isTherapist
                  ? "You don't have any assigned patients yet."
                  : "No patients yet."}
            </p>
            {!search && !zipCode && !isTherapist && (
              <Button asChild>
                <Link href="/patients/new">Add your first patient</Link>
              </Button>
            )}
          </div>
        )}

        {!loading && !error && data && data.items.length > 0 && (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Address</TableHead>
                  <TableHead>Visit Duration</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((patient) => (
                  <TableRow key={patient.id}>
                    <TableCell>
                      <Link href={`/patients/${patient.id}`} className="font-medium hover:underline">
                        {patient.first_name} {patient.last_name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {patient.address_line_1}, {patient.city}, {patient.state} {patient.zip_code}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {patient.visit_duration_minutes ? `${patient.visit_duration_minutes} min` : "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={patient.is_active ? "default" : "secondary"}>
                        {patient.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>
                Page {data.page} of {Math.max(data.total_pages, 1)} &middot; {data.total} total
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= data.total_pages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </main>
    </>
  );
}
