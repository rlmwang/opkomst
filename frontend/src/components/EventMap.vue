<script setup lang="ts">
import L from "leaflet";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import "leaflet/dist/leaflet.css";

const props = defineProps<{
  latitude: number;
  longitude: number;
}>();

// Leaflet's default marker icon paths break under bundlers because the
// CSS expects images at relative URLs. Re-bind them to URL-imported
// assets so the bundler resolves them. Using ?url so Vite copies the
// images into the output folder.
import iconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png";
import iconUrl from "leaflet/dist/images/marker-icon.png";
import shadowUrl from "leaflet/dist/images/marker-shadow.png";

L.Marker.prototype.options.icon = L.icon({
  iconRetinaUrl,
  iconUrl,
  shadowUrl,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  tooltipAnchor: [16, -28],
  shadowSize: [41, 41],
});

const mapEl = ref<HTMLDivElement | null>(null);
let map: L.Map | null = null;
let marker: L.Marker | null = null;

function render() {
  if (!mapEl.value) return;
  const center: L.LatLngExpression = [props.latitude, props.longitude];
  if (!map) {
    map = L.map(mapEl.value, { scrollWheelZoom: false, zoomControl: true }).setView(center, 16);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);
    marker = L.marker(center).addTo(map);
  } else {
    map.setView(center, 16);
    if (marker) marker.setLatLng(center);
  }
}

onMounted(render);
watch(() => [props.latitude, props.longitude] as const, render);
onBeforeUnmount(() => {
  if (map) {
    map.remove();
    map = null;
    marker = null;
  }
});
</script>

<template>
  <div ref="mapEl" class="event-map" />
</template>

<style scoped>
.event-map {
  height: 280px;
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--brand-border);
  overflow: hidden;
}
</style>
