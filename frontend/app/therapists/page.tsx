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
import { useRequireAuth } from "@/lib/use-require-auth";
import type { PaginatedResponse } from "@/types/patient";
import type { Therapist } from "@/types/therapist";

const PAGE_SIZE = 25;

export default function TherapistsListPage() {
  const { checked } = useRequireAuth();

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("active");
  const [page, setPage] = useState(1);

  const [data, setData] = useState<PaginatedResponse<Therapist> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTherapists = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (search.trim()) params.set("search", search.trim());
      if (statusFilter !== "all") params.set("is_active", statusFilter === "active" ? "true" : "false");

      const result = await apiFetch<PaginatedResponse<Therapist>>(`/therapists?${params.toString()}`);
      setData(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load therapists. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter]);

  useEffect(() => {
    if (checked) loadTherapists();
  }, [checked, loadTherapists]);

  function handleSearchSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPage(1);
    loadTherapists();
  }

  if (!checked) return null;

  return (
    <>
      <AppHeader />
      <main className="container space-y-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Therapists</h1>
            <p className="text-sm text-muted-foreground">Manage your clinic&apos;s therapists.</p>
          </div>
          <Button asChild>
            <Link href="/therapists/new">Add therapist</Link>
          </Button>
        </div>

        <form onSubmit={handleSearchSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <label className="text-sm font-medium" htmlFor="search">
              Search by name
            </label>
            <Input id="search" placeholder="e.g. Sarah Johnson" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:w-44">
            <label className="text-sm font-medium" htmlFor="status">
              Status
            </label>
            <select
              id="status"
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value as "all" | "active" | "inactive");
                setPage(1);
              }}
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="all">All</option>
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
              {search ? "No therapists match your search." : "No therapists yet."}
            </p>
            {!search && (
              <Button asChild>
                <Link href="/therapists/new">Add your first therapist</Link>
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
                  <TableHead>License</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>Max Daily Hours</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((therapist) => (
                  <TableRow key={therapist.id}>
                    <TableCell>
                      <Link href={`/therapists/${therapist.id}`} className="font-medium hover:underline">
                        {therapist.first_name} {therapist.last_name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{therapist.license_type || "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{therapist.phone || "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{therapist.max_daily_hours ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant={therapist.is_active ? "default" : "secondary"}>
                        {therapist.is_active ? "Active" : "Inactive"}
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
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                  Previous
                </Button>
                <Button variant="outline" size="sm" disabled={page >= data.total_pages} onClick={() => setPage((p) => p + 1)}>
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
