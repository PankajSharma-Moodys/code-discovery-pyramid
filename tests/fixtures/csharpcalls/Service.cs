using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Shop.Core;

namespace Shop.App;

public class Service : Base
{
    private readonly IStore _store;
    private readonly List<Widget> _cache = new();
    public Service(IStore store) : base(1) { _store = store; }

    public async Task<string> Run(string id)
    {
        var w = await _store.FindAsync(id);
        var p = new Plain();
        string s = $"{w.Label()} and {string.Join(",", _cache.Select(c => c.Label()))}";
        foreach (var item in _store.All()) { item.Shout(); }
        Widget made = Widget.Make("a");
        Widget other = new();
        var names = _store.All().Select(Convert);
        return Greet() + w.Shout() + s + made.Label() + other.Label() + p + names;
    }

    private static string Convert(Widget w) => w.Name;
}
