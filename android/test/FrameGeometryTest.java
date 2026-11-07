import com.tvgun.gun.Tracker;
import java.lang.reflect.Array;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Paths;

/** Check the updated normal-coordinate darkness sampling against generated fixtures. */
public class FrameGeometryTest {
    public static void main(String[] args) throws Exception {
        Class<?> edge = Class.forName("com.tvgun.gun.Tracker$EdgeMeas");
        Constructor<?> ctor = edge.getDeclaredConstructor();
        ctor.setAccessible(true);
        Class<?> arrayType = Array.newInstance(edge, 4).getClass();
        Method measure = Tracker.class.getDeclaredMethod("measureEdges", byte[].class, int.class, int.class,
                int.class, arrayType);
        measure.setAccessible(true);
        Field h = Tracker.class.getDeclaredField("H");
        h.setAccessible(true);
        for (int i = 0; i < 3; i++) {
            int white = new int[]{24, 40, 12}[i];
            int dark = new int[]{48, 24, 72}[i];
            Tracker tracker = new Tracker();
            tracker.setFrameGeometry(white, dark);
            h.set(tracker, new double[]{4, 0, -320, 0, 4, -180, 0, 0, 1});
            byte[] gray = Files.readAllBytes(Paths.get(args[0], "frame_" + i + ".bin"));
            Object edges = Array.newInstance(edge, 4);
            for (int j = 0; j < 4; j++) Array.set(edges, j, ctor.newInstance());
            int count = (Integer) measure.invoke(tracker, gray, 640, 360, 180, edges);
            if (count != 4) throw new AssertionError("FRAME " + white + "," + dark + ": edges=" + count);
            System.out.println("PASS FRAME " + white + "," + dark + " measured four edges");
        }
    }
}
