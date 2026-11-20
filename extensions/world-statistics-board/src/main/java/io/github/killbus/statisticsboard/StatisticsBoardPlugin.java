package io.github.killbus.statisticsboard;

import com.github.retrooper.packetevents.PacketEvents;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import net.kyori.adventure.text.Component;
import org.bukkit.Bukkit;
import org.bukkit.Statistic;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.PlayerDeathEvent;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerGameModeChangeEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.mvplugins.multiverse.core.MultiverseCoreApi;
import org.mvplugins.multiverse.inventories.MultiverseInventoriesApi;

public final class StatisticsBoardPlugin extends JavaPlugin implements Listener {
    private final Map<UUID, String> rejections = new HashMap<>();
    private StatisticsScopeResolver resolver;
    private SidebarProjection projection;
    private int maxRows;
    private boolean refreshPending;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        String title = getConfig().getString("title", "Deaths");
        maxRows = getConfig().getInt("max-rows", 15);
        int refreshTicks = getConfig().getInt("refresh-ticks", 20);
        if (title == null || title.isBlank() || maxRows < 1 || maxRows > 15 || refreshTicks < 1 || refreshTicks > 1200) {
            throw new IllegalArgumentException("title must be nonblank, max-rows 1..15 and refresh-ticks 1..1200");
        }
        var inventories = MultiverseInventoriesApi.get();
        resolver = new StatisticsScopeResolver(inventories.getInventoriesConfig(),
                inventories.getWorldGroupManager(), MultiverseCoreApi.get().getWorldManager());
        projection = new SidebarProjection(Component.text(title));
        PacketEvents.getAPI().getEventManager().registerListener(projection);
        Bukkit.getPluginManager().registerEvents(this, this);
        Bukkit.getScheduler().runTaskTimer(this, this::refresh, 1L, refreshTicks);
    }

    @Override
    public void onDisable() {
        if (projection == null) return;
        for (Player player : Bukkit.getOnlinePlayers()) projection.release(player);
        PacketEvents.getAPI().getEventManager().unregisterListener(projection);
    }

    private void refresh() {
        Map<String, List<SidebarProjection.Row>> rosters = new HashMap<>();
        Map<Player, String> viewers = new HashMap<>();
        for (Player player : Bukkit.getOnlinePlayers()) {
            var result = resolver.resolve(player);
            if (result.scope() == null) {
                projection.release(player);
                if (!result.reason().equals(rejections.put(player.getUniqueId(), result.reason()))) {
                    getLogger().warning("No statistics sidebar for " + player.getName() + ": " + result.reason());
                }
                continue;
            }
            rejections.remove(player.getUniqueId());
            viewers.put(player, result.scope());
            rosters.computeIfAbsent(result.scope(), ignored -> new ArrayList<>())
                    .add(new SidebarProjection.Row(player.getUniqueId(), player.getName(), player.getStatistic(Statistic.DEATHS)));
        }
        Map<String, List<SidebarProjection.Row>> selected = new HashMap<>();
        rosters.forEach((scope, rows) -> selected.put(scope, selectRows(rows, maxRows)));
        viewers.forEach((player, scope) -> projection.show(player, scope, selected.get(scope)));
    }

    static List<SidebarProjection.Row> selectRows(List<SidebarProjection.Row> rows, int limit) {
        return rows.stream().sorted(Comparator.comparingInt(SidebarProjection.Row::deaths).reversed()
                .thenComparing(SidebarProjection.Row::holder)).limit(limit).toList();
    }

    private void scheduleRefresh() {
        if (refreshPending) return;
        refreshPending = true;
        Bukkit.getScheduler().runTask(this, () -> {
            refreshPending = false;
            refresh();
        });
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void joined(PlayerJoinEvent event) {
        scheduleRefresh();
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void changed(PlayerChangedWorldEvent event) {
        scheduleRefresh();
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void changedMode(PlayerGameModeChangeEvent event) {
        scheduleRefresh();
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void died(PlayerDeathEvent event) {
        scheduleRefresh();
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void quit(PlayerQuitEvent event) {
        projection.forget(event.getPlayer().getUniqueId());
        rejections.remove(event.getPlayer().getUniqueId());
        scheduleRefresh();
    }
}
