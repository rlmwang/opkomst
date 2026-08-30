import type { Component } from "svelte";

import { brand } from "@/lib/branding";

/**
 * The app's router.
 *
 * Small on purpose: 32 flat routes, at most one parameter each, one
 * async guard, and lazily imported page components. vue-router was
 * 9.5 kB gzipped for that, and its history/base handling is the only
 * part worth keeping the shape of.
 *
 * The organiser app is served under its organisation's slug
 * (``opkomst.nu/rsp/event``), so every path is relative to that base. It
 * comes from the brand the server injected into the page head: the app
 * never parses it out of the URL, so a mismatch between what the page is
 * wearing and what it routes to is impossible. A page served in the
 * house brand belongs to no organisation and is based at ``/``.
 */
export interface RouteMeta {
  requiresAuth?: boolean;
  requiresApproved?: boolean;
  requiresAdmin?: boolean;
  requiresOrganisation?: boolean;
  /** At the root these are also the signed-out front door. */
  startable?: boolean;
  /** Which product a shared page is rendering. */
  resource?: "form" | "quiz" | "compass";
}

/**
 * A page.
 *
 * Its props are the route's parameters, and a page declares only the
 * ones its own path carries: the dashboard takes none, the event editor
 * takes an ``eventId``. There is no type that is both, so the table
 * holds them loosely and each page states what it needs.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type PageComponent = Component<any>;

export interface RouteDef {
  path: string;
  load: () => Promise<{ default: PageComponent }>;
  meta?: RouteMeta;
}

export interface Matched {
  path: string;
  params: Record<string, string>;
  meta: RouteMeta;
  component: PageComponent;
}

const BASE = brand().app_base.replace(/\/$/, "");

/** A path pattern to a matcher. ``:name`` captures one segment;
 *  ``*`` at the end catches everything left. */
function compile(pattern: string): { re: RegExp; keys: string[] } {
  const keys: string[] = [];
  const source = pattern
    .split("/")
    .map((part) => {
      if (part === "*") return "(?:.*)";
      if (part.startsWith(":")) {
        keys.push(part.slice(1));
        return "([^/]+)";
      }
      return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    })
    .join("/");
  return { re: new RegExp(`^${source}/?$`), keys };
}

/** Strip the organisation's prefix, so the table is written in plain
 *  paths and the base is a deployment detail. */
export function stripBase(pathname: string): string {
  if (BASE && pathname.startsWith(BASE)) return pathname.slice(BASE.length) || "/";
  return pathname || "/";
}

export function withBase(path: string): string {
  return `${BASE}${path}`;
}

export function matchRoute(routes: RouteDef[], path: string): { route: RouteDef; params: Record<string, string> } | null {
  for (const route of routes) {
    const { re, keys } = compile(route.path);
    const found = re.exec(path);
    if (!found) continue;
    const params: Record<string, string> = {};
    keys.forEach((key, i) => {
      params[key] = decodeURIComponent(found[i + 1] ?? "");
    });
    return { route, params };
  }
  return null;
}
