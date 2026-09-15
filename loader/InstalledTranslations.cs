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
        public static InstalledStore Deserialize(string text)
        {
            // The game's Mono JavaScriptSerializer calls Trim() in StoreKey,
            // corrupting exact-source dictionary keys that start/end in newlines.
            return ReadJson<InstalledStore>(text);
        }

        public static T ReadJson<T>(string text)
        {
            // Keep the game's existing reader, but protect BOTH ends of every
            // JSON object key from Mono's JsonDeserializer.StoreKey().Trim().
            // Tokenise whole strings first so quotes/colons inside values cannot
            // be mistaken for object keys. Values and escape sequences are exact.
            string protectedText = System.Text.RegularExpressions.Regex.Replace(text,
                "\"(?:\\\\.|[^\"\\\\])*\"", match => {
                    int next = match.Index + match.Length;
                    while (next < text.Length && Char.IsWhiteSpace(text[next])) next++;
                    return next < text.Length && text[next] == ':'
                        ? "\"~" + match.Value.Substring(1, match.Length - 2) + "~\"" : match.Value;
                });
            var reader = new System.Web.Script.Serialization.JavaScriptSerializer { MaxJsonLength = Int32.MaxValue };
            return reader.ConvertToType<T>(RestoreKeys(reader.DeserializeObject(protectedText)));
        }

        private static object RestoreKeys(object value)
        {
            var dictionary = value as IDictionary<string, object>;
            if (dictionary != null)
            {
                var restored = new Dictionary<string, object>(StringComparer.Ordinal);
                foreach (var pair in dictionary)
                {
                    if (pair.Key.Length < 2 || pair.Key[0] != '~' || pair.Key[pair.Key.Length - 1] != '~')
                        throw new System.IO.InvalidDataException("Malformed protected translation key.");
                    restored.Add(pair.Key.Substring(1, pair.Key.Length - 2), RestoreKeys(pair.Value));
                }
                return restored;
            }
            var list = value as System.Collections.IList;
            if (list != null)
            {
                var restored = new object[list.Count];
                for (int i = 0; i < list.Count; i++) restored[i] = RestoreKeys(list[i]);
                return restored;
            }
            return value;
        }

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
