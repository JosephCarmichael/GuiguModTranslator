using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using GuiguModTranslation;

static class CatalogTests
{
    static int count;
    static void Equal(string expected, string actual)
    {
        count++;
        if (actual != expected) throw new Exception("Expected " + expected + "; got " + actual);
    }
    static void Main(string[] args)
    {
        var catalog = new TranslationCatalog(new Dictionary<string, string> {
            {"宝剑", "Sword"}, {"<color=red>恢复{0}灵力</color>", "<color=red>Restore {0} spirit</color>"},
            {"{0}获得{1}件宝物", "{0} obtained {1} treasures"}, {"给{0}和{0}宝剑", "Give {0} and {0} a sword"},
            {"第一行\n第二行", "First line\nSecond line"} });
        Equal("Sword", catalog.Translate("宝剑"));
        Equal("宝剑碎片", catalog.Translate("宝剑碎片"));
        Equal(null, catalog.Translate(null));
        Equal("", catalog.Translate(""));
        Equal("English", catalog.Translate("English"));
        Equal("<color=red>Restore {0} spirit</color>", catalog.Translate("<color=red>恢复{0}灵力</color>"));
        Equal("<color=red>Restore 25 spirit</color>", catalog.Translate("<color=red>恢复25灵力</color>"));
        Equal("李明 obtained 3 treasures", catalog.Translate("李明获得3件宝物"));
        Equal("Give 张三 and 张三 a sword", catalog.Translate("给张三和张三宝剑"));
        Equal("给张三和李四宝剑", catalog.Translate("给张三和李四宝剑"));
        Equal("First line\nSecond line", catalog.Translate("第一行\n第二行"));
        Equal("宝剑 ", catalog.Translate("宝剑 "));
        Equal("<color=#ff0000>Sword</color>", catalog.Translate("<color=#ff0000>宝剑</color>"));
        Equal("<b> Sword </b>\r\nSword", catalog.Translate("<b> 宝剑 </b>\r\n宝剑"));
        Equal("<b>宝剑碎片</b>", catalog.Translate("<b>宝剑碎片</b>"));
        Equal("<sprite name=宝剑>Sword", catalog.Translate("<sprite name=宝剑>宝剑"));
        var ambiguous = new TranslationCatalog(new Dictionary<string, string> {
            {"恢复{0}灵力", "Restore {0}"}, {"恢复2{0}灵力", "Different {0}"} });
        Equal("恢复25灵力", ambiguous.Translate("恢复25灵力"));
        // Repeated lookups exercise the bounded cache too.
        Equal("<color=red>Restore 25 spirit</color>", catalog.Translate("<color=red>恢复25灵力</color>"));
        TestInstalledConflicts();
        if (args.Length == 2) TestLiveInventory(args[0], args[1]);
        Console.WriteLine(count + " catalog assertions passed.");
    }

    static void TestLiveInventory(string storePath, string inventoryPath)
    {
        var json = new JavaScriptSerializer { MaxJsonLength = Int32.MaxValue };
        var store = json.Deserialize<InstalledStore>(System.IO.File.ReadAllText(storePath));
        int conflicts;
        var entries = InstalledTranslations.Resolve(store, path => true, out conflicts);
        var catalog = new TranslationCatalog(entries);
        var inventory = (Dictionary<string, object>)json.DeserializeObject(System.IO.File.ReadAllText(inventoryPath));
        foreach (Dictionary<string, object> field in (object[])inventory["fields"])
        {
            string source = (string)field["source"], expected;
            if (!entries.TryGetValue(source, out expected)) continue;
            Equal(expected, catalog.Translate(source));
            if ((bool)field["missing"]) Console.WriteLine("Runtime mismatch: id=" + field["destiny_id"] + "; field=" + field["field"] + "; source length=" + source.Length);
        }
    }

    static void TestInstalledConflicts()
    {
        var older = new InstalledMod { source_path = "present", installed_at = "2026-09-13T10:00:00Z", install_order = 1,
            entries = new Dictionary<string, string> { { "宝剑", "Sword" }, { "灵力", "Spirit" } } };
        var newer = new InstalledMod { source_path = "present", installed_at = "2026-09-13T09:00:00Z", install_order = 2,
            entries = new Dictionary<string, string> { { "宝剑", "Treasure sword" }, { "灵力", "Spirit" } } };
        var store = new InstalledStore { format = "guigu-installed-v1", mods = new Dictionary<string, InstalledMod> {
            { "z-old", older }, { "a-new", newer } } };
        // Use the same serializer as the game; installation order beats clock changes.
        var json = new JavaScriptSerializer();
        store = json.Deserialize<InstalledStore>(json.Serialize(store));
        int conflicts;
        var resolved = InstalledTranslations.Resolve(store, path => path == "present", out conflicts);
        Equal("Treasure sword", new TranslationCatalog(resolved).Translate("宝剑"));
        Equal("1", conflicts.ToString());
        Equal("Sword", store.mods["z-old"].entries["宝剑"]);
        store.mods["a-new"].source_path = "missing";
        Equal("Sword", InstalledTranslations.Resolve(store, path => path == "present", out conflicts)["宝剑"]);
        Equal("0", conflicts.ToString());
        store.mods["a-new"].source_path = "present";
        store.mods["z-old"].install_order = 3;
        Equal("Sword", InstalledTranslations.Resolve(store, path => true, out conflicts)["宝剑"]);
        store.mods.Remove("z-old");
        Equal("Treasure sword", InstalledTranslations.Resolve(store, path => true, out conflicts)["宝剑"]);
        // Legacy dictionaries have no sequence. Timestamp, then ordinal mod ID,
        // resolves priority consistently regardless of JSON dictionary order.
        older.install_order = newer.install_order = 0;
        store.mods = new Dictionary<string, InstalledMod> { { "a", newer }, { "z", older } };
        Equal("Sword", InstalledTranslations.Resolve(store, path => true, out conflicts)["宝剑"]);
        older.installed_at = newer.installed_at = null;
        Equal("Treasure sword", InstalledTranslations.Resolve(store, path => true, out conflicts)["宝剑"]);
        store.mods = new Dictionary<string, InstalledMod> { { "z", older }, { "a", newer } };
        Equal("Treasure sword", InstalledTranslations.Resolve(store, path => true, out conflicts)["宝剑"]);
        newer.entries["宝剑"] = " ";
        Equal("Sword", InstalledTranslations.Resolve(store, path => true, out conflicts)["宝剑"]);
    }
}
