import { describe, expect, it } from "vitest";
import { mapLink } from "@/lib/map-link";

describe("mapLink", () => {
  it("drops a marker pin when coords are present", () => {
    const url = mapLink({ location: "Vleutenseweg, Utrecht", latitude: 52.0907, longitude: 5.1214 });
    expect(url).toContain("mlat=52.0907");
    expect(url).toContain("mlon=5.1214");
    expect(url).toContain("#map=18/52.0907/5.1214");
  });

  it("falls back to OSM search when coords are missing", () => {
    const url = mapLink({ location: "Vleutenseweg, Utrecht", latitude: null, longitude: null });
    expect(url).toContain("/search?query=");
    expect(url).toContain(encodeURIComponent("Vleutenseweg, Utrecht"));
  });
});
