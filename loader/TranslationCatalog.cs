using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace GuiguModTranslation
{
    // Independent of Unity so the same matching code can be tested offline.
    public sealed class TranslationCatalog
    {
        private readonly Dictionary<string, string> exact;
        private readonly List<Template> templates = new List<Template>();
        private readonly Dictionary<string, string> cache = new Dictionary<string, string>(StringComparer.Ordinal);
        private static readonly Regex Slots = new Regex(@"\{(\d+)\}");
        private static readonly Regex PresentationParts = new Regex(@"(<(?:/?(?:color|size|b|i|u|s|r|g|alpha|align|font|sprite|br)\b[^<>\r\n]*|\#[0-9a-f]{3,8})>|\r\n|\r|\n)", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
        public int Count { get { return exact.Count; } }

        public object Diagnose(string text)
        {
            Func<string, string> normal = s => s.Replace("\\r\\n", "\n").Replace("\\n", "\n").Replace("\r\n", "\n").Replace("\r", "\n");
            string candidate = exact.Keys.FirstOrDefault(k => normal(k) == normal(text));
            return new { source_length = text.Length, source_prefix = text.Take(8).Select(c => (int)c).ToArray(),
                exact_match = exact.ContainsKey(text), normalized_match = candidate != null,
                candidate_length = candidate == null ? -1 : candidate.Length,
                candidate_prefix = candidate == null ? new int[0] : candidate.Take(8).Select(c => (int)c).ToArray() };
        }

        public TranslationCatalog(Dictionary<string, string> entries)
        {
            exact = new Dictionary<string, string>(entries, StringComparer.Ordinal);
            foreach (var pair in entries.OrderByDescending(p => p.Key.Length).ThenBy(p => p.Key, StringComparer.Ordinal))
            {
                var matches = Slots.Matches(pair.Key);
                if (matches.Count == 0 || pair.Key.Length > 8192) continue;
                // A literal anchor is required; never treat a bare placeholder as display text.
                if (Slots.Replace(pair.Key, "").Length < 2) continue;
                var pattern = new StringBuilder("\\A");
                var groups = new HashSet<string>();
                int cursor = 0;
                foreach (Match match in matches)
                {
                    pattern.Append(Regex.Escape(pair.Key.Substring(cursor, match.Index - cursor)));
                    string name = "v" + match.Groups[1].Value;
                    pattern.Append(groups.Add(name) ? "(?<" + name + ">.+?)" : "\\k<" + name + ">");
                    cursor = match.Index + match.Length;
                }
                pattern.Append(Regex.Escape(pair.Key.Substring(cursor))).Append("\\z");
                templates.Add(new Template { Prefix = pair.Key.Substring(0, matches[0].Index),
                    Pattern = new Regex(pattern.ToString(), RegexOptions.Singleline | RegexOptions.CultureInvariant,
                                        TimeSpan.FromMilliseconds(10)), Target = pair.Value });
            }
        }

        public string Translate(string text)
        {
            string result = TranslateCore(text);
            if (String.IsNullOrEmpty(text) || result != text || text.Length > 8192 || !HasChinese(text)) return result;
            // Only complete text runs between formatting/line boundaries. Never
            // replace a known name inside a longer unrelated Chinese word.
            var parts = PresentationParts.Split(text);
            if (parts.Length == 1) return result;
            for (int i = 0; i < parts.Length; i += 2)
            {
                string part = parts[i], trimmed = part.Trim();
                string translated = TranslateCore(trimmed);
                if (translated != trimmed)
                {
                    int start = part.IndexOf(trimmed, StringComparison.Ordinal);
                    parts[i] = part.Substring(0, start) + translated + part.Substring(start + trimmed.Length);
                }
            }
            return String.Concat(parts);
        }

        private string TranslateCore(string text)
        {
            if (String.IsNullOrEmpty(text)) return text;
            string found;
            if (exact.TryGetValue(text, out found)) return found;
            if (text.Length > 8192 || !HasChinese(text)) return text;
            if (cache.TryGetValue(text, out found)) return found;
            string result = text;
            foreach (var template in templates)
            {
                if (!text.StartsWith(template.Prefix, StringComparison.Ordinal)) continue;
                try
                {
                    var match = template.Pattern.Match(text);
                    if (!match.Success) continue;
                    var candidate = Slots.Replace(template.Target, slot => match.Groups["v" + slot.Groups[1].Value].Value);
                    // Ambiguous formatted text is left alone rather than selecting an arbitrary mod.
                    if (result != text && result != candidate) { result = text; break; }
                    result = candidate;
                }
                catch (RegexMatchTimeoutException) { }
            }
            if (cache.Count >= 4096) cache.Clear();
            cache[text] = result;
            return result;
        }

        public static bool HasChinese(string value)
        {
            if (value == null) return false;
            foreach (char c in value) if (c >= '\u3400' && c <= '\u9fff' || c >= '\uf900' && c <= '\ufaff') return true;
            return false;
        }
        private sealed class Template { public string Prefix; public Regex Pattern; public string Target; }
    }
}
