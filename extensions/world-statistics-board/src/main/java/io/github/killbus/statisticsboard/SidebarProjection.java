package io.github.killbus.statisticsboard;

import com.github.retrooper.packetevents.PacketEvents;
import com.github.retrooper.packetevents.event.PacketListenerAbstract;
import com.github.retrooper.packetevents.event.PacketListenerPriority;
import com.github.retrooper.packetevents.event.PacketSendEvent;
import com.github.retrooper.packetevents.protocol.packettype.PacketType;
import com.github.retrooper.packetevents.wrapper.PacketWrapper;
import com.github.retrooper.packetevents.wrapper.play.server.WrapperPlayServerDisplayScoreboard;
import com.github.retrooper.packetevents.wrapper.play.server.WrapperPlayServerResetScore;
import com.github.retrooper.packetevents.wrapper.play.server.WrapperPlayServerScoreboardObjective;
import com.github.retrooper.packetevents.wrapper.play.server.WrapperPlayServerUpdateScore;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import net.kyori.adventure.text.Component;
import org.bukkit.entity.Player;
import org.bukkit.scoreboard.DisplaySlot;

final class SidebarProjection extends PacketListenerAbstract {
    private final Map<UUID, View> views = new ConcurrentHashMap<>();
    private final Component title;

    SidebarProjection(Component title) {
        super(PacketListenerPriority.HIGHEST);
        this.title = title;
    }

    @Override
    public void onPacketSend(PacketSendEvent event) {
        if (event.getPacketType() != PacketType.Play.Server.DISPLAY_SCOREBOARD
                && event.getPacketType() != PacketType.Play.Server.SCOREBOARD_OBJECTIVE) return;
        if (event.getUser() == null || event.getUser().getUUID() == null) return;
        UUID player = event.getUser().getUUID();
        View view = views.get(player);
        if (view == null || event.isCancelled()) return;
        if (event.getPacketType() == PacketType.Play.Server.DISPLAY_SCOREBOARD) {
            var display = new WrapperPlayServerDisplayScoreboard(event);
            if (sidebar(display.getPosition()) && !view.objective.equals(display.getScoreName())) {
                synchronized (view) {
                    if (views.get(player) != view) return;
                    view.nativeSlots.put(display.getPosition(), display.getScoreName());
                    event.setCancelled(true);
                }
            }
        } else if (event.getPacketType() == PacketType.Play.Server.SCOREBOARD_OBJECTIVE) {
            var objective = new WrapperPlayServerScoreboardObjective(event);
            if (objective.getMode() == WrapperPlayServerScoreboardObjective.ObjectiveMode.REMOVE) {
                synchronized (view) {
                    if (views.get(player) != view) return;
                    view.nativeSlots.replaceAll((slot, name) -> name.equals(objective.getName()) ? "" : name);
                }
            }
        }
    }

    void show(Player player, String scope, List<Row> rows) {
        View view = views.get(player.getUniqueId());
        if (view == null) {
            view = new View("msb_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12));
            for (DisplaySlot slot : DisplaySlot.values()) {
                int position = position(slot);
                if (!sidebar(position)) continue;
                var objective = player.getScoreboard().getObjective(slot);
                view.nativeSlots.put(position, objective == null ? "" : objective.getName());
            }
            views.put(player.getUniqueId(), view);
            send(player, new WrapperPlayServerScoreboardObjective(view.objective,
                    WrapperPlayServerScoreboardObjective.ObjectiveMode.CREATE, title,
                    WrapperPlayServerScoreboardObjective.RenderType.INTEGER));
            for (int slot = 3; slot <= 18; slot++) {
                send(player, new WrapperPlayServerDisplayScoreboard(slot, ""));
            }
            send(player, new WrapperPlayServerDisplayScoreboard(1, view.objective));
        }
        if (!scope.equals(view.scope)) {
            for (String previous : view.rows.keySet()) {
                send(player, new WrapperPlayServerResetScore(previous, view.objective));
            }
            view.rows = Map.of();
            view.scope = scope;
        }
        Map<String, Row> next = new HashMap<>();
        for (Row row : rows) next.put(row.holder(), row);
        for (String previous : view.rows.keySet()) {
            if (!next.containsKey(previous)) {
                send(player, new WrapperPlayServerResetScore(previous, view.objective));
            }
        }
        for (Row row : rows) {
            if (!row.equals(view.rows.get(row.holder()))) {
                send(player, new WrapperPlayServerUpdateScore(row.holder(),
                        WrapperPlayServerUpdateScore.Action.CREATE_OR_UPDATE_ITEM,
                        view.objective, row.deaths(), Component.text(row.name()), null));
            }
        }
        view.rows = next;
    }

    void release(Player player) {
        View view = views.get(player.getUniqueId());
        if (view == null) return;
        synchronized (view) {
            views.remove(player.getUniqueId(), view);
            send(player, new WrapperPlayServerScoreboardObjective(view.objective,
                    WrapperPlayServerScoreboardObjective.ObjectiveMode.REMOVE, title,
                    WrapperPlayServerScoreboardObjective.RenderType.INTEGER));
            view.nativeSlots.forEach((slot, name) -> send(player, new WrapperPlayServerDisplayScoreboard(slot, name)));
        }
    }

    void forget(UUID player) {
        views.remove(player);
    }

    private static boolean sidebar(int slot) {
        return slot == 1 || slot >= 3 && slot <= 18;
    }

    private static int position(DisplaySlot slot) {
        return switch (slot) {
            case PLAYER_LIST -> 0;
            case SIDEBAR -> 1;
            case BELOW_NAME -> 2;
            case SIDEBAR_TEAM_BLACK -> 3;
            case SIDEBAR_TEAM_DARK_BLUE -> 4;
            case SIDEBAR_TEAM_DARK_GREEN -> 5;
            case SIDEBAR_TEAM_DARK_AQUA -> 6;
            case SIDEBAR_TEAM_DARK_RED -> 7;
            case SIDEBAR_TEAM_DARK_PURPLE -> 8;
            case SIDEBAR_TEAM_GOLD -> 9;
            case SIDEBAR_TEAM_GRAY -> 10;
            case SIDEBAR_TEAM_DARK_GRAY -> 11;
            case SIDEBAR_TEAM_BLUE -> 12;
            case SIDEBAR_TEAM_GREEN -> 13;
            case SIDEBAR_TEAM_AQUA -> 14;
            case SIDEBAR_TEAM_RED -> 15;
            case SIDEBAR_TEAM_LIGHT_PURPLE -> 16;
            case SIDEBAR_TEAM_YELLOW -> 17;
            case SIDEBAR_TEAM_WHITE -> 18;
        };
    }

    private static void send(Player player, PacketWrapper<?> packet) {
        PacketEvents.getAPI().getPlayerManager().sendPacketSilently(player, packet);
    }

    record Row(UUID player, String name, int deaths) {
        String holder() {
            return "msb:" + player.toString();
        }
    }

    private static final class View {
        private final String objective;
        private final Map<Integer, String> nativeSlots = new HashMap<>();
        private Map<String, Row> rows = Map.of();
        private String scope;

        private View(String objective) {
            this.objective = objective;
        }
    }
}
