using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using UnityEngine;

namespace GuiguModTranslation
{
    public sealed partial class TranslationMod
    {
        private static readonly HashSet<string> destinyKeys = new HashSet<string>(StringComparer.Ordinal);
        private static readonly Dictionary<string, string> destinyFallbacks = new Dictionary<string, string>(StringComparer.Ordinal);
        private static readonly HashSet<string> observedUntranslated = new HashSet<string>(StringComparer.Ordinal);
        private static bool creatorOpen;
        [ThreadStatic] private static bool readingDestinySource;
        private List<DestinyField> destinyFields = new List<DestinyField>();
        private List<DestinyField> pendingDestinyFields;
        private readonly Dictionary<string, List<DestinyField>> emptyDestinyFields = new Dictionary<string, List<DestinyField>>(StringComparer.Ordinal);
        private int localTextCursor;
        private int destinyCursor, pendingDestinyCount, destinyCount;
        private float nextDestinyScan = 10;
        private string destinyCapturedAt;

        private static bool IsDestinyDisplay(Component component)
        {
            var parent = component == null ? null : component.transform;
            for (int depth = 0; parent != null && depth < 16; depth++, parent = parent.parent)
            {
                string name = parent.name.ToLowerInvariant();
                if (name.Contains("luck") || name.Contains("tips") || name.Contains("tooltip")) return true;
            }
            return false;
        }

        private void PatchDestinyLocalization()
        {
            try
            {
                foreach (var method in typeof(GameTool).GetMethods().Where(m =>
                    (m.Name == "LS" || m.Name == "LSTextReplaceColor") && m.ReturnType == typeof(string) &&
                    m.GetParameters().Length > 0 && m.GetParameters()[0].ParameterType == typeof(string)))
                {
                    HarmonyInstance.Patch(method, postfix: new HarmonyMethod(typeof(TranslationMod), nameof(AfterDestinyLocalization)));
                    hooks.Add("Destiny localisation: " + method);
                }
            }
            catch (Exception error) { errors.Add("Destiny localisation: " + error.Message); }
        }

        public static void AfterDestinyLocalization(string __0, ref string __result)
        {
            if (readingDestinySource || __0 == null) return;
            try
            {
                lock (Gate)
                {
                    if (!destinyKeys.Contains(__0)) return;
                    string source = __result, fallback;
                    if ((String.IsNullOrEmpty(source) || source == __0) && destinyFallbacks.TryGetValue(__0, out fallback)) source = fallback;
                    var translated = catalog.Translate(source);
                    if (translated != __result) { __result = translated; hits++; }
                }
            }
            catch { }
        }

        private void UpdateDestinyCapture()
        {
            try
            {
                creatorOpen = g.ui != null && g.ui.GetUI<UICreatePlayer>(UIType.CreatePlayer) != null;
                if (pendingDestinyFields == null && Time.realtimeSinceStartup < nextDestinyScan) return;
                var rows = g.conf?.roleCreateFeature?._allConfList;
                if (rows == null || rows.Count == 0)
                { nextDestinyScan = Time.realtimeSinceStartup + 5; return; }
                if (pendingDestinyFields == null)
                {
                    pendingDestinyFields = new List<DestinyField>();
                    emptyDestinyFields.Clear();
                    localTextCursor = 0;
                    destinyCursor = pendingDestinyCount = 0;
                }
                // Spread native localisation calls over frames, including unrolled destinies.
                int end = Math.Min(rows.Count, destinyCursor + 32);
                for (; destinyCursor < end; destinyCursor++)
                {
                    var row = rows[destinyCursor];
                    if (row == null || row.type != 1) continue;
                    pendingDestinyCount++;
                    CaptureDestinyField(row.id, "name", row.name);
                    CaptureDestinyField(row.id, "tips", row.tips);
                    CaptureDestinyField(row.id, "introduceText", row.introduceText);
                }
                if (destinyCursor >= rows.Count)
                {
                    if (!ResolveEmptyDestinyFields()) return;
                    destinyFields = pendingDestinyFields;
                    pendingDestinyFields = null;
                    destinyCount = pendingDestinyCount;
                    destinyCapturedAt = DateTime.UtcNow.ToString("o");
                    nextDestinyScan = Time.realtimeSinceStartup + 30;
                    WriteDestinyInventory();
                }
            }
            catch (Exception error)
            {
                pendingDestinyFields = null;
                nextDestinyScan = Time.realtimeSinceStartup + 30;
                if (errors.Count < 20) errors.Add("Destiny inventory: " + error);
            }
        }

        private void CaptureDestinyField(int id, string field, string key)
        {
            if (String.IsNullOrEmpty(key) || key == "0") return;
            string source;
            readingDestinySource = true;
            try { source = TranslationCatalog.HasChinese(key) ? key : GameTool.LS(key); }
            finally { readingDestinySource = false; }
            bool unresolved = !TranslationCatalog.HasChinese(key) && (String.IsNullOrEmpty(source) || source == key);
            string translated;
            lock (Gate)
            {
                destinyKeys.Add(key);
                if (!unresolved && !String.IsNullOrEmpty(source)) destinyFallbacks[key] = source;
                translated = catalog.Translate(source);
            }
            var entry = new DestinyField { destiny_id = id.ToString(), field = field, key = key, source = source ?? "",
                translated = translated ?? "", unresolved = unresolved, missing = unresolved || TranslationCatalog.HasChinese(translated) };
            pendingDestinyFields.Add(entry);
            if (unresolved)
            {
                List<DestinyField> entries;
                if (!emptyDestinyFields.TryGetValue(key, out entries)) emptyDestinyFields[key] = entries = new List<DestinyField>();
                entries.Add(entry);
            }
        }

        private bool ResolveEmptyDestinyFields()
        {
            if (emptyDestinyFields.Count == 0) return true;
            // Unhollower's native Dictionary.TryGetValue<T> out-value bridge
            // throws "TValue_REF..ctor(intptr)" on this game. Use the concrete
            // localisation row list instead, with a bounded per-frame budget.
            var rows = g.conf?.localText?.allConfList;
            if (rows == null) return true;
            int end = Math.Min(rows.Count, localTextCursor + 1024);
            for (; localTextCursor < end; localTextCursor++)
            {
                var row = rows[localTextCursor];
                List<DestinyField> fields;
                if (row == null || row.key == null || !emptyDestinyFields.TryGetValue(row.key, out fields)) continue;
                string source = !String.IsNullOrEmpty(row.en) ? row.en : !String.IsNullOrEmpty(row.ch) ? row.ch : row.tc ?? "";
                foreach (var entry in fields)
                {
                    entry.source = source;
                    entry.unresolved = false; // An all-empty row is intentionally blank.
                    lock (Gate)
                    {
                        if (!String.IsNullOrEmpty(source)) destinyFallbacks[entry.key] = source;
                        entry.translated = catalog.Translate(source);
                    }
                    entry.missing = TranslationCatalog.HasChinese(entry.translated);
                }
                emptyDestinyFields.Remove(row.key);
            }
            return emptyDestinyFields.Count == 0 || localTextCursor >= rows.Count;
        }

        private sealed class DestinyField
        {
            public string destiny_id, field, key, source, translated;
            public bool unresolved, missing;
        }

        private object ProbeDestinyLocalization()
        {
            var samples = destinyFields.Where(f => !f.unresolved && TranslationCatalog.HasChinese(f.source)).ToArray();
            var results = new List<object>();
            foreach (var entry in samples)
            {
                string actual = GameTool.LS(entry.key);
                results.Add(new { entry.destiny_id, entry.field, entry.key, entry.source,
                    expected = entry.translated, actual, passed = actual == entry.translated && !TranslationCatalog.HasChinese(actual),
                    diagnostics = entry.missing ? catalog.Diagnose(entry.source) : null });
            }
            return new { destiny_count = destinyCount, fields = destinyFields.Count, samples = results };
        }

        private void WriteDestinyInventory()
        {
            if (destinyCapturedAt == null) return;
            string[] observed;
            lock (Gate) observed = observedUntranslated.OrderBy(x => x, StringComparer.Ordinal).ToArray();
            WriteJson("destiny-inventory.json", new { format = "guigu-destinies-v1",
                process_id = System.Diagnostics.Process.GetCurrentProcess().Id, captured_at_utc = destinyCapturedAt,
                destiny_count = destinyCount, fields = destinyFields, observed_untranslated = observed,
                observation_limit_reached = observed.Length >= 5000 });
            if (System.IO.File.Exists(System.IO.Path.Combine(directory, "diagnostics-request.json")))
                WriteJson("runtime-match-diagnostics.json", new { process_id = System.Diagnostics.Process.GetCurrentProcess().Id,
                    fields = destinyFields.Where(f => f.missing && !f.unresolved).Take(10).Select(f => new {
                        f.destiny_id, f.field, f.source, diagnostics = catalog.Diagnose(f.source) }).ToArray() });
        }
    }
}
