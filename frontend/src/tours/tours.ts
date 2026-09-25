import type { Tour, TourId } from "./types";

/**
 * The six tours, as data. The step tables are ``docs/design-tour.md``
 * chapter 4; the words are ``tour.*`` in the locale files.
 */

const next = { kind: "next" } as const;
const click = { kind: "click" } as const;

export const TOURS: Record<TourId, Tour> = {
  // Signed out, on the landing page. Lights the whole form rather than
  // the button, because the person has to type in a field a smaller
  // hole would leave under the mask. Ends before the inbox, which no
  // tour can follow anyone into.
  inloggen: {
    id: "inloggen",
    perPage: false,
    steps: [
      { page: "/", anchor: "door.form", advance: next },
      { page: "/", anchor: "door.form", advance: { kind: "until", name: "door.sent" } },
      { page: "/", anchor: "door.sent", advance: next },
      { page: "/", anchor: "door.sent", advance: next },
    ],
  },
  // Offered once. Follows the person from the landing page to their
  // first event's details page; its third step ends when the share
  // link exists there, so it neither guesses when the save landed nor
  // advances on a click inside the form that was not the save.
  welkom: {
    id: "welkom",
    perPage: false,
    steps: [
      { page: "/", anchor: "home.events", advance: click },
      { page: "/event", anchor: "list.new", advance: click },
      { page: "/event/new", anchor: "form.card", advance: { kind: "until", name: "share.link" } },
      { page: "/event/:id", anchor: "share.link", advance: next },
      { page: "/event/:id", anchor: "header.menu", advance: next },
    ],
  },
  // A pointing tour: the archive step must not be a click, or the
  // tour would archive the person's first event to show archiving.
  lijst: {
    id: "lijst",
    perPage: true,
    steps: [
      { anchor: "list.new", advance: next },
      { anchor: "row.details", advance: next },
      { anchor: "share.link", advance: next },
      { anchor: "row.archive", advance: next },
      { anchor: "list.archived", advance: next },
    ],
  },
  details: {
    id: "details",
    perPage: true,
    steps: [
      { anchor: "details.signups", advance: next },
      { anchor: "share.link", advance: next },
      { anchor: "share.qr", advance: next },
      { anchor: "details.edit", advance: next },
      { anchor: "details.feedback", advance: next },
    ],
  },
  formulier: {
    id: "formulier",
    perPage: true,
    steps: [
      { anchor: "form.section.first", advance: next },
      { anchor: "form.section.own", advance: next },
      { anchor: "form.fold", advance: click },
      { anchor: "form.fold.first", advance: next },
      { anchor: "form.submit", advance: next },
    ],
  },
  // One list, three admin pages: on each, the steps for that page are
  // the ones that show.
  beheer: {
    id: "beheer",
    perPage: true,
    steps: [
      { anchor: "admin.approve", advance: next },
      { anchor: "header.subtabs", advance: next },
      { anchor: "admin.chapter.new", advance: next },
      { anchor: "admin.chapter.row", advance: next },
      { anchor: "admin.agenda", advance: next },
    ],
  },
};
