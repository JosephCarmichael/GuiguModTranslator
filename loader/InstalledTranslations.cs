using System;
using System.Collections.Generic;
using System.Linq;

namespace GuiguModTranslation
{
    public sealed class InstalledStore
    {
        public string format { get; set; }
        public Dictionary<string, InstalledMod> mods { get; set; }
    }
    public sealed class InstalledMod
    {
        public string name { get; set; }
        public string source_path { get; set; }
        public string installed_at { get; set; }
        public long install_order { get; set; }
        public Dictionary<string, string> entries { get; set; }
    }

    public static class InstalledTranslations
    {
        public static Dictionary<string, string> Resolve(InstalledStore store, Func<string, bool> sourceExists, out int conflictsResolved)
        {
            var entries = new Dictionary<string, string>(StringComparer.Ordinal);
            var conflicts = new HashSet<string>(StringComparer.Ordinal);
            foreach (var mod in store.mods.OrderByDescending(p => p.Value.install_order)
                     .ThenByDescending(p => p.Value.installed_at ?? "", StringComparer.Ordinal)
                     .ThenBy(p => p.Key, StringComparer.Ordinal))
            {
                if (!sourceExists(mod.Value.source_path)) continue;
                foreach (var entry in mod.Value.entries)
                {
                    if (String.IsNullOrEmpty(entry.Key) || String.IsNullOrWhiteSpace(entry.Value)) continue;
                    string previous;
                    if (entries.TryGetValue(entry.Key, out previous))
                    {
                        if (previous != entry.Value) conflicts.Add(entry.Key);
                    }
                    else entries.Add(entry.Key, entry.Value);
                }
            }
            conflictsResolved = conflicts.Count;
            return entries;
        }
    }
}
