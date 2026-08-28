# Bilingual titles and descriptions

An organiser can write the title and the description of anything they
make in Dutch, in English, or in both.

Both languages are columns on the entity (`name_nl` / `name_en`,
`description_nl` / `description_en`), with a check constraint that at
least one name is present. There is no translation table: two languages
are two columns, and a third would be a different design rather than
another row.

Every entity also carries its own `locale`. That decides which language
the public page opens in and which template its mail uses. It is a
property of the thing, not of whoever is reading it: an event written in
English stays English for everybody.

A page falls back to the other language rather than showing an empty
title. The editor shows the pair side by side, so a half-translated
entity is visible as such while it is being written.
