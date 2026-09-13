using System;
using System.Collections.Generic;
using GuiguModTranslation;

static class CatalogTests
{
    static int count;
    static void Equal(string expected, string actual)
    {
        count++;
        if (actual != expected) throw new Exception("Expected " + expected + "; got " + actual);
    }
    static void Main()
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
        var ambiguous = new TranslationCatalog(new Dictionary<string, string> {
            {"恢复{0}灵力", "Restore {0}"}, {"恢复2{0}灵力", "Different {0}"} });
        Equal("恢复25灵力", ambiguous.Translate("恢复25灵力"));
        // Repeated lookups exercise the bounded cache too.
        Equal("<color=red>Restore 25 spirit</color>", catalog.Translate("<color=red>恢复25灵力</color>"));
        Console.WriteLine(count + " catalog assertions passed.");
    }
}
