package svc.b;

public class Util {
    static void audit() { Metrics.bump("b"); }
}
