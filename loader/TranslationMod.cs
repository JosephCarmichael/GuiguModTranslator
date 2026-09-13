using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using HarmonyLib;
using MelonLoader;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

[assembly: MelonInfo(typeof(GuiguModTranslation.TranslationMod), "Guigu Mod Translation", "1.1.0", "GuiguModTranslator")]
[assembly: MelonGame(null, null)]

namespace GuiguModTranslation
{
    public sealed class TranslationMod : MelonMod
    {
        private static TranslationCatalog catalog = new TranslationCatalog(new Dictionary<string, string>());
        private static long hits;
        private static readonly object Gate = new object();
        private readonly List<string> hooks = new List<string>();
        private readonly List<string> errors = new List<string>();
        private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = Int32.MaxValue };
        private string directory;
        private string storeHash;
        private float nextSweep = 10;
        private float nextStatus = 5;
        private bool probeDone;
        private int conflictsResolved;

        public override void OnApplicationStart()
        {
            directory = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "UserData", "GuiguModTranslator");
            Directory.CreateDirectory(directory);
            try
            {
                string file = Path.Combine(directory, "installed.json");
                if (File.Exists(file))
                {
                    byte[] bytes = File.ReadAllBytes(file);
                    using (var sha = SHA256.Create()) storeHash = BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
                    var store = json.Deserialize<InstalledStore>(Encoding.UTF8.GetString(bytes));
                    if (store.format != "guigu-installed-v1" || store.mods == null) throw new InvalidDataException("Unknown installed dictionary format.");
                    var entries = InstalledTranslations.Resolve(store,
                        path => Directory.Exists(path) || File.Exists(path), out conflictsResolved);
                    if (conflictsResolved > 0) LoggerInstance.Msg("Automatically resolved " + conflictsResolved + " text conflicts using installation priority.");
                    catalog = new TranslationCatalog(entries);
                }
                Patch(AccessTools.PropertySetter(typeof(Text), "text"));
                Patch(AccessTools.PropertySetter(typeof(TMP_Text), "text"));
                Patch(AccessTools.PropertySetter(typeof(TextMesh), "text"));
                // TMP SetText can bypass the text property, including its numeric formatting overloads.
                foreach (var method in typeof(TMP_Text).GetMethods(BindingFlags.Public | BindingFlags.Instance))
                    if (method.Name == "SetText" && method.GetParameters().Length > 0 && method.GetParameters()[0].ParameterType == typeof(string)) Patch(method);
            }
            catch (Exception error) { errors.Add(error.ToString()); LoggerInstance.Error(error.ToString()); }
            WriteStatus();
            LoggerInstance.Msg("Loaded " + catalog.Count + " translations; " + hooks.Count + " text hooks. Restart the game after installation changes.");
        }

        private void Patch(MethodInfo method)
        {
            if (method == null) return;
            try
            {
                HarmonyInstance.Patch(method, prefix: new HarmonyMethod(typeof(TranslationMod), nameof(BeforeText)));
                hooks.Add(method.DeclaringType.FullName + "." + method);
            }
            catch (Exception error) { errors.Add(method.Name + ": " + error.Message); }
        }

        public static void BeforeText(ref string __0)
        {
            // A display hook must never break the original UI update.
            try
            {
                lock (Gate)
                {
                    string translated = catalog.Translate(__0);
                    if (translated != __0) { __0 = translated; hits++; }
                }
            }
            catch { }
        }

        public override void OnUpdate()
        {
            if (Time.realtimeSinceStartup >= nextSweep)
            {
                nextSweep = Time.realtimeSinceStartup + 3;
                try
                {
                    // Serialized prefab text and TMP character arrays can bypass setters.
                    foreach (var text in UnityEngine.Object.FindObjectsOfType<Text>())
                    { string value = text.text, translated = value; BeforeText(ref translated); if (translated != value) text.text = translated; }
                    foreach (var text in UnityEngine.Object.FindObjectsOfType<TMP_Text>())
                    { string value = text.text, translated = value; BeforeText(ref translated); if (translated != value) text.text = translated; }
                    foreach (var text in UnityEngine.Object.FindObjectsOfType<TextMesh>())
                    { string value = text.text, translated = value; BeforeText(ref translated); if (translated != value) text.text = translated; }
                }
                catch (Exception error) { if (errors.Count < 20) errors.Add(error.Message); }
            }
            if (!probeDone && Time.realtimeSinceStartup > 20 && Environment.GetCommandLineArgs().Contains("--guigu-translation-probe"))
            { probeDone = true; Probe(); }
            if (Time.realtimeSinceStartup >= nextStatus)
            { nextStatus = Time.realtimeSinceStartup + 10; WriteStatus(); }
        }

        private void WriteStatus()
        {
            try
            {
                WriteJson("runtime-status.json", new { version = "1.1.0", process_id = System.Diagnostics.Process.GetCurrentProcess().Id,
                    loaded_at_utc = DateTime.UtcNow.ToString("o"), entries = catalog.Count, hits, conflicts_resolved = conflictsResolved, store_sha256 = storeHash, hooks, errors });
            }
            catch { }
        }
        private void WriteJson(string name, object value)
        {
            string file = Path.Combine(directory, name), temp = file + ".tmp";
            File.WriteAllText(temp, json.Serialize(value), new UTF8Encoding(false));
            if (File.Exists(file)) File.Replace(temp, file, null); else File.Move(temp, file);
        }

        private void Probe()
        {
            // Explicit test mode only. Real Unity components exercise the installed native hooks.
            var objects = new List<GameObject>();
            try
            {
                var samples = json.Deserialize<Dictionary<string, string>>(File.ReadAllText(Path.Combine(directory, "probe-request.json")));
                var results = new List<object>();
                foreach (var sample in samples)
                {
                    var go = new GameObject("GuiguTranslationProbe"); objects.Add(go);
                    var text = go.AddComponent<Text>(); text.text = sample.Key;
                    var tmpGo = new GameObject("GuiguTranslationProbeTMP"); objects.Add(tmpGo);
                    var tmp = tmpGo.AddComponent<TextMeshProUGUI>(); tmp.text = sample.Key;
                    string property = tmp.text;
                    tmp.SetText(sample.Key, true);
                    results.Add(new { source = sample.Key, expected = sample.Value, ugui = text.text, tmp = property, tmp_settext = tmp.text,
                        passed = text.text == sample.Value && property == sample.Value && tmp.text == sample.Value });
                }
                WriteJson("probe-result.json", new { entries = catalog.Count, hooks, errors, results });
            }
            catch (Exception error) { WriteJson("probe-result.json", new { error = error.ToString() }); }
            finally { foreach (var go in objects) UnityEngine.Object.Destroy(go); }
        }
    }
}
