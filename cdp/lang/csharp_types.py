"""C# names and the little the extractor knows about the BCL.

A type is a string like the Java one: `Ns.Foo`, `System.Collections.Generic.List<Ns.Foo>`,
`Ns.Foo[]`, `~T` for a type variable. Names are the extractor's best guess (a type of this file,
an alias, a well-known BCL type, else the file's own namespace); the resolve phase, which owns the
symbol table, settles them. The BCL model is what chained calls, `await` and lambdas need: what a
collection, `Task<T>`, `IOptions<T>` or a LINQ stage hands back.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .java_types import split_type

PRIMS = frozenset(["int", "long", "double", "float", "bool", "byte", "sbyte", "short", "ushort", "uint",
                   "ulong", "char", "decimal", "string", "object", "void", "var", "dynamic", "nint", "nuint"])
_NS = {
    "System.Collections.Generic": "List IList ICollection IEnumerable IEnumerator IReadOnlyList IReadOnlyCollection "
                                  "IReadOnlyDictionary Dictionary IDictionary HashSet ISet Queue Stack LinkedList "
                                  "KeyValuePair SortedDictionary SortedSet IAsyncEnumerable IComparer IEqualityComparer",
    "System.Collections.ObjectModel": "Collection ReadOnlyCollection ObservableCollection ReadOnlyDictionary",
    "System.Collections.Concurrent": "ConcurrentDictionary ConcurrentQueue ConcurrentBag ConcurrentStack",
    "System.Collections.Immutable": "ImmutableList ImmutableArray ImmutableHashSet ImmutableDictionary",
    "System.Threading.Tasks": "Task ValueTask TaskCompletionSource",
    "System.Linq": "IQueryable IOrderedQueryable IOrderedEnumerable IGrouping ILookup Enumerable Queryable",
    "System": "String Guid DateTime DateTimeOffset TimeSpan Lazy Func Action Tuple ValueTuple Nullable Exception Uri "
              "Math Convert Environment Console Array Object Type Version Random BitConverter Buffer Span "
              "ReadOnlySpan Memory ArgumentException ArgumentNullException InvalidOperationException Enum GC",
    "System.Text": "StringBuilder Encoding",
    "System.Threading": "CancellationToken CancellationTokenSource Interlocked Monitor SemaphoreSlim Thread Timer",
    "System.IO": "File Path Directory Stream StreamReader StreamWriter MemoryStream",
    "Microsoft.Extensions.Options": "IOptions IOptionsSnapshot IOptionsMonitor Options",
    "Microsoft.Extensions.Configuration": "IConfiguration IConfigurationSection IConfigurationRoot ConfigurationBuilder",
    "Microsoft.Extensions.Logging": "ILogger ILoggerFactory",
    "Microsoft.EntityFrameworkCore": "DbSet DbContext DatabaseFacade EntityState",
}
BCL: Dict[str, str] = {n: ns for ns, names in _NS.items() for n in names.split()}

ENUMERABLE = frozenset(["List", "IList", "ICollection", "IEnumerable", "IReadOnlyList", "IReadOnlyCollection", "HashSet",
                        "ISet", "Queue", "Stack", "LinkedList", "IAsyncEnumerable", "IQueryable", "IOrderedQueryable",
                        "IOrderedEnumerable", "DbSet", "ImmutableList", "ImmutableArray", "ImmutableHashSet",
                        "Collection", "ReadOnlyCollection", "ObservableCollection", "SortedSet", "ConcurrentQueue",
                        "ConcurrentBag", "ConcurrentStack", "IEnumerator", "Span", "ReadOnlySpan"])
MAPS = frozenset(["Dictionary", "IDictionary", "IReadOnlyDictionary", "SortedDictionary", "ConcurrentDictionary",
                  "ImmutableDictionary", "ReadOnlyDictionary"])
GROUPS = frozenset(["IGrouping", "ILookup"])
TASKS = frozenset(["Task", "ValueTask"])
VALUE_PROP = {"Lazy": "Value", "IOptions": "Value", "IOptionsSnapshot": "Value", "IOptionsMonitor": "CurrentValue",
              "Nullable": "Value", "ValueTuple": None}
ELEMENT_OF = frozenset(["First", "FirstOrDefault", "Single", "SingleOrDefault", "Last", "LastOrDefault", "ElementAt",
                        "ElementAtOrDefault", "Peek", "Dequeue", "Pop", "Min", "Max", "Find", "MinBy", "MaxBy"])
SAME_TYPE = frozenset(["Where", "OrderBy", "OrderByDescending", "ThenBy", "ThenByDescending", "Skip", "Take", "Distinct",
                       "Reverse", "AsEnumerable", "AsNoTracking", "AsTracking", "Include", "ThenInclude", "AsQueryable",
                       "Except", "Union", "Concat", "SkipWhile", "TakeWhile", "Intersect", "DistinctBy", "OrderDescending",
                       "Order", "AsSplitQuery", "IgnoreQueryFilters", "TagWith"])
LAMBDA_ELEMENT = frozenset(["Where", "Select", "SelectMany", "Any", "All", "First", "FirstOrDefault", "Single",
                            "SingleOrDefault", "Last", "LastOrDefault", "Count", "LongCount", "OrderBy", "OrderByDescending",
                            "ThenBy", "ThenByDescending", "GroupBy", "ForEach", "FindAll", "Find", "Exists", "RemoveAll",
                            "Sum", "Max", "Min", "Average", "TakeWhile", "SkipWhile", "ToDictionary", "ToLookup", "Include",
                            "ThenInclude", "FindIndex", "TrueForAll", "MaxBy", "MinBy", "DistinctBy", "Aggregate",
                            "FirstOrDefaultAsync", "FirstAsync", "SingleOrDefaultAsync", "SingleAsync", "AnyAsync",
                            "AllAsync", "CountAsync", "SumAsync", "MaxAsync", "MinAsync", "LastOrDefaultAsync",
                            "ExecuteDeleteAsync", "ExecuteUpdateAsync", "Join", "Zip", "Except", "Contains"])
ASYNC_SUFFIX = {"FirstOrDefaultAsync": "FirstOrDefault", "FirstAsync": "First", "SingleOrDefaultAsync": "SingleOrDefault",
                "SingleAsync": "Single", "LastOrDefaultAsync": "LastOrDefault", "ToListAsync": "ToList",
                "ToArrayAsync": "ToArray", "FindAsync": "Find"}
STEP_LISTS = {"ToList": "List", "ToArray": None, "ToHashSet": "HashSet"}


def simple(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def canon_bcl(name: str) -> Optional[str]:
    ns = BCL.get(name)
    return (ns + "." + name) if ns else None


def is_bcl(base: str) -> bool:
    base = split_type(base)[0]
    s = simple(base)
    if s in BCL and (base.startswith(("System", "Microsoft")) or "." not in base):
        return True
    return s == "ValueTuple"


def _wrap(ns_name: str, *args: str) -> str:
    return "%s<%s>" % (ns_name, ",".join(args))


def bcl_step(type_str: str, step: str) -> Optional[str]:
    """The type `step` produces from `type_str`. Steps: `m:name` call, `f:name` member, `e` element,
    `k`/`v` map key/value, `a` index, `w` await."""
    base, args, arrays = split_type(type_str)
    if arrays:
        if step in ("a", "e"):
            return type_str[:-2]
        if step.startswith("m:") and step[2:] in ELEMENT_OF:
            return type_str[:-2]
        if step.startswith("m:") and step[2:] in SAME_TYPE | {"ToList"}:
            return _wrap("System.Collections.Generic.IEnumerable", type_str[:-2])
        return None
    s = simple(base)
    first = args[0] if args else None
    if step == "w":
        return first if s in TASKS and first else None
    if s in TASKS:
        if step == "f:Result" and first:
            return first
        if step.startswith("m:") and step[2:] in ("ConfigureAwait", "AsTask"):
            return type_str
        if step == "m:GetAwaiter":
            return type_str
        if step == "m:GetResult" and first:
            return first
        return None
    if s in ENUMERABLE:
        if step in ("e",) and first:
            return first
        if step == "a":
            return first if s not in ("HashSet", "ISet", "Queue", "Stack", "IEnumerable") else None
        if not step.startswith("m:") or not first:
            return None
        name = step[2:]
        task = name in ASYNC_SUFFIX
        name = ASYNC_SUFFIX.get(name, name)
        if name in ELEMENT_OF:
            out = first
        elif name in SAME_TYPE:
            out = _wrap("System.Collections.Generic.IEnumerable", first)
        elif name == "ToList":
            out = _wrap("System.Collections.Generic.List", first)
        elif name == "ToArray":
            out = first + "[]"
        elif name == "ToHashSet":
            out = _wrap("System.Collections.Generic.HashSet", first)
        elif name in ("GetEnumerator",):
            out = _wrap("System.Collections.Generic.IEnumerator", first)
        else:
            return None
        return _wrap("System.Threading.Tasks.Task", out) if task else out
    if s in MAPS and len(args) == 2:
        if step == "e":
            return _wrap("System.Collections.Generic.KeyValuePair", *args)
        if step == "k":
            return args[0]
        if step in ("v", "a"):
            return args[1]
        if step == "f:Values":
            return _wrap("System.Collections.Generic.ICollection", args[1])
        if step == "f:Keys":
            return _wrap("System.Collections.Generic.ICollection", args[0])
        return None
    if s == "KeyValuePair" and len(args) == 2:
        return args[0] if step == "f:Key" else args[1] if step == "f:Value" else None
    if s in GROUPS and len(args) == 2:
        if step == "f:Key":
            return args[0]
        if step == "e":
            return args[1]
        return None
    if s in VALUE_PROP and first and step == "f:" + str(VALUE_PROP[s]):
        return first
    return None


class Resolver:
    """Simple name -> FQN within one file's own knowledge."""

    def __init__(self, ns: str, usings: List[str], aliases: Dict[str, str]) -> None:
        self.pkg = ns
        self.aliases = aliases
        self.local_types: Dict[str, str] = {}
        parents: List[str] = []
        cur = ns
        while cur:
            parents.append(cur)
            cur = cur.rsplit(".", 1)[0] if "." in cur else ""
        # enclosing namespaces (innermost first), then `using` namespaces
        self.wildcards: List[str] = parents[1:] + [u for u in usings if u not in parents]
        self.simple_to_fqn: Dict[str, str] = dict(aliases)

    def resolve(self, name: str) -> Tuple[str, str]:
        name = name.strip().split("<", 1)[0].strip().replace("[]", "").strip()
        if name.startswith("global::"):
            return name[8:], "external"
        if not name or name in PRIMS:
            return name, "third_party"
        head, dot, rest = name.partition(".")
        if head in self.local_types:
            return self.local_types[head] + dot + rest, "external"
        if head in self.aliases:
            return self.aliases[head] + dot + rest, "external"
        if dot:
            canon = canon_bcl(head) if head in BCL and not rest[:1].islower() else None
            return (canon + dot + rest if canon else name), "external"
        bcl = canon_bcl(name)
        if bcl:
            return bcl, "third_party"
        if self.pkg:
            return self.pkg + "." + name, "local"
        return name, "unresolved"


def norm_type(text: str, resolve, tvars=frozenset()) -> str:
    from .java_types import norm_type as nt
    return nt(text.replace("?", ""), resolve, tvars)


MOQ_LAMBDA = frozenset(["Setup", "SetupGet", "SetupSet", "Verify", "VerifyGet", "SetupSequence", "VerifySet"])
# Instance members of BCL types a call on a BCL receiver is far more likely to be than a repository
# extension method; a name outside this set on a BCL receiver is recorded for the resolve phase.
BCL_MEMBERS = frozenset((
    "Add AddRange Remove RemoveAt RemoveAll RemoveRange Clear Contains ContainsKey ContainsValue TryGetValue TryAdd "
    "TryRemove TryPeek TryDequeue TryPop TryParse Insert InsertRange IndexOf LastIndexOf Sort Reverse CopyTo ToString "
    "Equals GetHashCode GetType CompareTo Dispose Close Flush Read ReadAsync ReadLine ReadLineAsync ReadToEnd "
    "ReadToEndAsync Write WriteAsync WriteLine WriteLineAsync Append AppendLine AppendFormat Substring Split Trim "
    "TrimStart TrimEnd ToUpper ToLower ToUpperInvariant ToLowerInvariant StartsWith EndsWith Replace PadLeft PadRight "
    "Format Join Concat Compare Normalize Enqueue Dequeue Peek Push Pop GetEnumerator MoveNext Reset Cancel CancelAfter "
    "Wait WaitAsync Release Set Acquire Run Delay WhenAll WhenAny FromResult ContinueWith ConfigureAwait GetAwaiter "
    "GetResult Start Join Abort Interrupt Invoke BeginInvoke EndInvoke DynamicInvoke Select SelectMany Where Any All "
    "First FirstOrDefault Single SingleOrDefault Last LastOrDefault Count LongCount Sum Min Max Average Aggregate "
    "OrderBy OrderByDescending ThenBy ThenByDescending GroupBy Join GroupJoin Distinct DistinctBy Except Intersect "
    "Union Concat Zip Skip Take SkipWhile TakeWhile ToList ToArray ToDictionary ToHashSet ToLookup Cast OfType "
    "AsEnumerable AsQueryable ElementAt ElementAtOrDefault DefaultIfEmpty SequenceEqual Prepend Chunk MinBy MaxBy "
    "ForEach Find FindAll FindIndex FindLast Exists TrueForAll ConvertAll AsReadOnly ToImmutableList "
    "ToListAsync ToArrayAsync FirstOrDefaultAsync FirstAsync SingleOrDefaultAsync SingleAsync AnyAsync AllAsync "
    "CountAsync SumAsync MaxAsync MinAsync LastOrDefaultAsync AddAsync AddRangeAsync SaveChanges SaveChangesAsync "
    "Include ThenInclude AsNoTracking AsTracking Entry Attach Update UpdateRange RemoveRange FindAsync Set "
    "ExecuteDeleteAsync ExecuteUpdateAsync OrderByAsync Load LoadAsync "
    "GetValue GetSection GetChildren GetConnectionString Bind Get GetRequiredService GetService GetServices "
    "Log LogInformation LogWarning LogError LogDebug LogTrace LogCritical BeginScope IsEnabled "
    "GetString GetBytes GetInt32 GetInt64 GetBoolean GetDateTime GetDecimal GetDouble GetGuid GetOrdinal IsDBNull "
    "ExecuteReader ExecuteReaderAsync ExecuteNonQuery ExecuteNonQueryAsync ExecuteScalar ExecuteScalarAsync "
    "CreateCommand BeginTransaction BeginTransactionAsync Commit CommitAsync Rollback RollbackAsync Open OpenAsync "
    "CreateDirectory Delete Exists Copy Move Create CreateText Seek SetLength Resize Slice AsSpan AsMemory ToCharArray "
    "Parse ToInt32 ToInt64 ToBoolean ToDateTime ToDecimal ToDouble ToBase64String FromBase64String AddDays AddHours "
    "AddMinutes AddSeconds AddMilliseconds AddMonths AddYears Subtract ToUniversalTime ToLocalTime TotalSeconds "
    "GetOrAdd AddOrUpdate GetOrCreate Next NextDouble NextBytes IsNullOrEmpty IsNullOrWhiteSpace Deconstruct "
    "WithCancellation GetAsync PostAsync PutAsync DeleteAsync SendAsync GetStringAsync GetStreamAsync GetByteArrayAsync "
    "ReadAsStringAsync ReadAsStreamAsync ReadAsByteArrayAsync ReadFromJsonAsync PostAsJsonAsync PutAsJsonAsync "
    "EnsureSuccessStatusCode Throw ThrowIfNull ThrowIfCancellationRequested Register GetFileName GetDirectoryName "
    "Combine GetExtension GetFullPath HasValue GetValueOrDefault CopyToAsync ToUri ToTitleCase Lock Enter Exit "
    "AddSingleton AddScoped AddTransient AddHostedService AddOptions Configure AddLogging AddHttpClient "
    "AddControllers AddAuthentication AddAuthorization AddCors AddDbContext "
    "UseRouting UseEndpoints UseAuthentication UseAuthorization UseCors UseHttpsRedirection UseSwagger UseSwaggerUI "
    "MapControllers MapGet MapPost MapPut MapDelete Map Run Build CreateBuilder CreateLogger Ok BadRequest NotFound "
    "Fail Success Equal NotEqual True False Null NotNull Empty NotEmpty Same Throws ThrowsAsync Contains DoesNotContain "
    "IsType IsAssignableFrom InRange Single Collection Setup Returns ReturnsAsync Verify Callback "
    "VerifyAll Throws ThrowsAsync It IsAny Is Mock Object"
).split())


ELEMENT_COLLECTIONS = frozenset(["List", "IList", "ICollection", "IEnumerable", "IReadOnlyList", "IReadOnlyCollection",
                                 "HashSet", "ISet", "Queue", "Stack", "LinkedList", "Collection", "ObservableCollection",
                                 "ImmutableList", "ImmutableArray", "ConcurrentBag", "SortedSet", "ReadOnlyCollection"])


def strip_path_args(text: str) -> str:
    """`Transform<A>.Comparison` -> `Transform.Comparison`: the arguments of an outer type never
    name the nested one."""
    out: List[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "<":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ">" and depth:
            depth -= 1
            if depth == 0:
                if text[i + 1:i + 2] == ".":
                    continue
                out.append(text[start:i + 1])
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)
