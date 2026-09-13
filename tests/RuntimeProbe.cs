// Test-only Melon mod; never included in the translator distribution.
using System;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;
using MelonLoader;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

[assembly: MelonInfo(typeof(GuiguTranslationProbe), "Guigu Translation Test Probe", "1.0.0", "GuiguModTranslator Tests")]
[assembly: MelonGame(null, null)]

public sealed class GuiguTranslationProbe : MelonMod
{
    bool done;
    public override void OnUpdate()
    {
        if (done || Time.realtimeSinceStartup < 35) return;
        done = true;
        string directory = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "UserData", "GuiguModTranslator");
        var json = new JavaScriptSerializer();
        try
        {
            var samples = json.Deserialize<Dictionary<string, string>>(File.ReadAllText(Path.Combine(directory, "probe-request.json")));
            var canvasGo = new GameObject("TranslationRuntimeEvidence");
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 32000;
            var panelGo = new GameObject("Panel"); panelGo.transform.SetParent(canvasGo.transform, false);
            var panel = panelGo.AddComponent<Image>(); panel.color = new Color(0.03f, 0.04f, 0.09f, 1);
            panel.rectTransform.anchorMin = new Vector2(0, 0); panel.rectTransform.anchorMax = new Vector2(1, 1);
            panel.rectTransform.offsetMin = new Vector2(20, 20); panel.rectTransform.offsetMax = new Vector2(-20, -20);
            var results = new List<object>();
            int line = 0;
            AddLabel(panelGo, "Guigu Mod Translator — native Unity text verification", line++);
            foreach (var sample in samples)
            {
                var text = AddLabel(panelGo, sample.Key, line++);
                var tmpGo = new GameObject("TMPProbe");
                var tmp = tmpGo.AddComponent<TextMeshProUGUI>();
                tmp.text = sample.Key;
                string property = tmp.text;
                tmp.SetText(sample.Key, true);
                bool passed = text.text == sample.Value && property == sample.Value && tmp.text == sample.Value;
                results.Add(new { source = sample.Key, expected = sample.Value, ugui = text.text,
                    tmp = property, tmp_settext = tmp.text, passed });
                UnityEngine.Object.Destroy(tmpGo);
            }
            AddLabel(panelGo, "Each line above was supplied to Unity in Chinese.", line++);
            AddLabel(panelGo, "UGUI + TMP property + TMP SetText results saved to probe-result.json", line);
            File.WriteAllText(Path.Combine(directory, "probe-result.json"), json.Serialize(new { results }));
        }
        catch (Exception error) { File.WriteAllText(Path.Combine(directory, "probe-result.json"), json.Serialize(new { error = error.ToString() })); }
    }
    static Text AddLabel(GameObject parent, string value, int line)
    {
        var go = new GameObject("ProbeLine" + line); go.transform.SetParent(parent.transform, false);
        var text = go.AddComponent<Text>();
        text.font = Resources.GetBuiltinResource<Font>("Arial.ttf");
        text.fontSize = 20; text.color = Color.white;
        text.horizontalOverflow = HorizontalWrapMode.Wrap;
        text.verticalOverflow = VerticalWrapMode.Overflow;
        text.rectTransform.anchorMin = new Vector2(0, 1); text.rectTransform.anchorMax = new Vector2(1, 1);
        text.rectTransform.pivot = new Vector2(0.5f, 1);
        text.rectTransform.offsetMin = new Vector2(25, -55 - line * 55);
        text.rectTransform.offsetMax = new Vector2(-25, -15 - line * 55);
        text.text = value;
        return text;
    }
}
