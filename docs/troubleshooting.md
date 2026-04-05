# Troubleshooting

## Common Issues

### Integration not found after installation

**Symptom:** After installing via HACS or manually, "EyeOnWater" doesn't appear in the Add Integration dialog.

**Solution:**
1. Verify the files are in `config/custom_components/eyeonwater/`.
2. Restart Home Assistant (a full restart, not just "Reload").
3. Clear your browser cache and hard-refresh the page.

---

### Login fails with valid credentials

**Symptom:** The config flow rejects your username/password even though they work on the EyeOnWater website.

**Solution:**
- Make sure your Home Assistant **country** setting matches your EyeOnWater account region (US vs. Canada). The integration uses `eyeonwater.com` for US and `eyeonwater.ca` for Canada.
- Check that your password doesn't contain characters that might be misinterpreted (try resetting it to a simple alphanumeric password).
- Check Home Assistant logs for the specific error message.

---

### No data in the Energy Dashboard

**Symptom:** The Energy Dashboard shows "No data" or empty graphs even after setup.

**Solution:**
1. Make sure you selected the **`eyeonwater:water_meter_xxxxx`** statistic (not `sensor.water_meter_xxxxx`).
2. Run the [import_historical_data service](historical-data.md) to backfill past data.
3. Wait a few hours — EyeOnWater publishes data with a delay.
4. Check **Developer Tools** → **Statistics** to verify the `eyeonwater:` statistics exist.

---

### Negative water usage spikes

**Symptom:** The Energy Dashboard shows negative consumption values.

**Solution:** This was a known issue in versions ≤ 2.5.x. [Upgrade to v2.6.0+](migration-v2.6.md) and follow the migration guide.

---

### Sensors show "Unavailable"

**Symptom:** The water meter sensor or diagnostic sensors show "Unavailable."

**Solution:**
- Check your internet connection and that EyeOnWater's website is accessible.
- Check Home Assistant logs (`Settings` → `System` → `Logs`, filter for `eyeonwater`) for API errors.
- The EyeOnWater service may be temporarily down — wait and try again.

---

### Diagnostic sensors not appearing

**Symptom:** You only see the main water meter sensor, not the temperature/flow/battery/signal sensors.

**Solution:** Diagnostic sensors are only created when the meter provides the corresponding data. Not all meters support all diagnostic data. If your meter doesn't report temperature or battery, those sensors won't appear.

---

## Getting Help

- Search [existing issues](https://github.com/kdeyev/eyeonwater/issues) on GitHub.
- Open a [new issue](https://github.com/kdeyev/eyeonwater/issues/new/choose) with your HA version, integration version, and relevant logs.
- Include logs from **Settings** → **System** → **Logs** (filter for `eyeonwater`).
