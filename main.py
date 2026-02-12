"""
Classic 2D Raycasting Demo (DOOM/Wolfenstein-style pseudo-3D)
=============================================================

Requirements:
- Python 3.8+
- pygame

Run:
    pip install pygame
    python main.py

Controls:
- W / S: Move forward / backward
- A / D: Strafe left / right
- Left / Right Arrow: Rotate
- Mouse X movement: Rotate
- ESC: Quit

Notes:
- This uses 2D raycasting math only (no OpenGL and no 3D engine).
- The "3D" scene is rendered manually as vertical wall slices.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass

import pygame


# -----------------------------
# Game / Render configuration
# -----------------------------
SCREEN_WIDTH = 960
SCREEN_HEIGHT = 600
HALF_HEIGHT = SCREEN_HEIGHT // 2
FPS_TARGET = 60

FOV_SCALE = 0.66  # Camera plane magnitude controls field of view (~66°)
MOVE_SPEED = 3.5  # world units / second
ROT_SPEED = 2.2   # radians / second

MINIMAP_SCALE = 12
MINIMAP_PADDING = 12

CEILING_COLOR = (50, 60, 90)
FLOOR_COLOR = (35, 30, 24)
BG_TEXT_COLOR = (220, 220, 220)

# 0 = empty space, 1 = wall
WORLD_MAP = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1],
    [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1],
    [1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 1],
    [1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 1],
    [1, 0, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1],
    [1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1],
    [1, 0, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],
    [1, 0, 1, 1, 1, 1, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
]
MAP_W = len(WORLD_MAP[0])
MAP_H = len(WORLD_MAP)


@dataclass
class Player:
    """Player state for raycasting camera and movement."""

    x: float
    y: float
    dir_x: float
    dir_y: float
    plane_x: float
    plane_y: float

    def rotate(self, angle: float) -> None:
        """Rotate direction and camera plane by angle (radians)."""
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        old_dir_x = self.dir_x
        self.dir_x = self.dir_x * cos_a - self.dir_y * sin_a
        self.dir_y = old_dir_x * sin_a + self.dir_y * cos_a

        old_plane_x = self.plane_x
        self.plane_x = self.plane_x * cos_a - self.plane_y * sin_a
        self.plane_y = old_plane_x * sin_a + self.plane_y * cos_a


def is_wall(x: float, y: float) -> bool:
    """Return True when a world position overlaps a wall cell or outside map."""
    map_x = int(x)
    map_y = int(y)
    if map_x < 0 or map_x >= MAP_W or map_y < 0 or map_y >= MAP_H:
        return True
    return WORLD_MAP[map_y][map_x] != 0


def try_move(player: Player, dx: float, dy: float) -> None:
    """Move with axis-separated collision so player cannot pass through walls."""
    new_x = player.x + dx
    new_y = player.y + dy

    # X axis collision
    if not is_wall(new_x, player.y):
        player.x = new_x

    # Y axis collision
    if not is_wall(player.x, new_y):
        player.y = new_y


def shade_by_distance(base_color: tuple[int, int, int], distance: float, side: int) -> tuple[int, int, int]:
    """Darken walls as they get farther away; side hits are slightly darker."""
    # Nonlinear falloff tuned for gameplay visibility.
    brightness = max(0.15, 1.0 / (1.0 + distance * 0.12))
    if side == 1:
        brightness *= 0.78

    r = int(base_color[0] * brightness)
    g = int(base_color[1] * brightness)
    b = int(base_color[2] * brightness)
    return r, g, b


def cast_and_render_walls(screen: pygame.Surface, player: Player) -> None:
    """Cast one ray per screen column and draw scaled vertical wall slices."""
    base_wall_color = (180, 145, 110)

    for x in range(SCREEN_WIDTH):
        # camera_x is in range [-1, +1], mapping current column to camera space.
        camera_x = 2.0 * x / SCREEN_WIDTH - 1.0

        # Ray direction = forward direction + camera plane offset.
        ray_dir_x = player.dir_x + player.plane_x * camera_x
        ray_dir_y = player.dir_y + player.plane_y * camera_x

        # Current map square of the player.
        map_x = int(player.x)
        map_y = int(player.y)

        # Distance to next x/y grid boundary.
        delta_dist_x = abs(1.0 / ray_dir_x) if ray_dir_x != 0 else 1e30
        delta_dist_y = abs(1.0 / ray_dir_y) if ray_dir_y != 0 else 1e30

        # Step direction and initial sideDist setup.
        if ray_dir_x < 0:
            step_x = -1
            side_dist_x = (player.x - map_x) * delta_dist_x
        else:
            step_x = 1
            side_dist_x = (map_x + 1.0 - player.x) * delta_dist_x

        if ray_dir_y < 0:
            step_y = -1
            side_dist_y = (player.y - map_y) * delta_dist_y
        else:
            step_y = 1
            side_dist_y = (map_y + 1.0 - player.y) * delta_dist_y

        # DDA loop: walk grid cell-by-cell until wall hit.
        hit = False
        side = 0  # 0 = x-side hit, 1 = y-side hit
        while not hit:
            if side_dist_x < side_dist_y:
                side_dist_x += delta_dist_x
                map_x += step_x
                side = 0
            else:
                side_dist_y += delta_dist_y
                map_y += step_y
                side = 1

            if map_x < 0 or map_x >= MAP_W or map_y < 0 or map_y >= MAP_H:
                hit = True
                break
            if WORLD_MAP[map_y][map_x] > 0:
                hit = True

        # Perpendicular distance avoids fisheye distortion.
        if side == 0:
            perp_wall_dist = (map_x - player.x + (1 - step_x) / 2) / (ray_dir_x if ray_dir_x != 0 else 1e-8)
        else:
            perp_wall_dist = (map_y - player.y + (1 - step_y) / 2) / (ray_dir_y if ray_dir_y != 0 else 1e-8)
        perp_wall_dist = max(perp_wall_dist, 1e-4)

        # Wall height is inversely proportional to distance.
        line_height = int(SCREEN_HEIGHT / perp_wall_dist)
        draw_start = max(0, -line_height // 2 + HALF_HEIGHT)
        draw_end = min(SCREEN_HEIGHT - 1, line_height // 2 + HALF_HEIGHT)

        color = shade_by_distance(base_wall_color, perp_wall_dist, side)
        pygame.draw.line(screen, color, (x, draw_start), (x, draw_end))


def draw_minimap(screen: pygame.Surface, player: Player) -> None:
    """Top-down minimap in the corner."""
    map_pixel_w = MAP_W * MINIMAP_SCALE
    map_pixel_h = MAP_H * MINIMAP_SCALE

    # Background panel
    panel_rect = pygame.Rect(
        MINIMAP_PADDING - 4,
        MINIMAP_PADDING - 4,
        map_pixel_w + 8,
        map_pixel_h + 8,
    )
    pygame.draw.rect(screen, (20, 20, 20), panel_rect)

    # Cells
    for y in range(MAP_H):
        for x in range(MAP_W):
            cell = WORLD_MAP[y][x]
            rect = pygame.Rect(
                MINIMAP_PADDING + x * MINIMAP_SCALE,
                MINIMAP_PADDING + y * MINIMAP_SCALE,
                MINIMAP_SCALE,
                MINIMAP_SCALE,
            )
            if cell == 1:
                pygame.draw.rect(screen, (120, 120, 120), rect)
            else:
                pygame.draw.rect(screen, (45, 45, 45), rect)

    # Player
    px = MINIMAP_PADDING + int(player.x * MINIMAP_SCALE)
    py = MINIMAP_PADDING + int(player.y * MINIMAP_SCALE)
    pygame.draw.circle(screen, (255, 80, 80), (px, py), 4)

    # Direction line
    dx = int(player.dir_x * 12)
    dy = int(player.dir_y * 12)
    pygame.draw.line(screen, (255, 220, 100), (px, py), (px + dx, py + dy), 2)


def draw_hud(screen: pygame.Surface, clock: pygame.time.Clock, font: pygame.font.Font) -> None:
    fps_text = f"FPS: {clock.get_fps():5.1f}"
    controls_text = "W/S move  A/D strafe  Mouse/Arrows rotate  ESC quit"

    fps_surf = font.render(fps_text, True, BG_TEXT_COLOR)
    controls_surf = font.render(controls_text, True, BG_TEXT_COLOR)

    screen.blit(fps_surf, (12, SCREEN_HEIGHT - 52))
    screen.blit(controls_surf, (12, SCREEN_HEIGHT - 28))


def handle_input(player: Player, dt: float) -> bool:
    """Handle events and keyboard/mouse input. Returns False when quitting."""
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return False

    keys = pygame.key.get_pressed()

    move_step = MOVE_SPEED * dt
    rot_step = ROT_SPEED * dt

    # Forward/backward
    if keys[pygame.K_w]:
        try_move(player, player.dir_x * move_step, player.dir_y * move_step)
    if keys[pygame.K_s]:
        try_move(player, -player.dir_x * move_step, -player.dir_y * move_step)

    # Strafing with vector perpendicular to direction
    if keys[pygame.K_a]:
        try_move(player, -player.dir_y * move_step, player.dir_x * move_step)
    if keys[pygame.K_d]:
        try_move(player, player.dir_y * move_step, -player.dir_x * move_step)

    # Arrow rotation
    if keys[pygame.K_LEFT]:
        player.rotate(-rot_step)
    if keys[pygame.K_RIGHT]:
        player.rotate(rot_step)

    # Mouse X movement controls rotation
    mouse_dx, _ = pygame.mouse.get_rel()
    if mouse_dx != 0:
        player.rotate(mouse_dx * 0.0022)

    return True


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Python Raycasting Demo")

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 20)

    # Hide mouse cursor and lock for FPS-like control.
    pygame.mouse.set_visible(False)
    pygame.event.set_grab(True)
    pygame.mouse.get_rel()  # Reset relative motion accumulator.

    # Start facing west, with camera plane defining FOV.
    player = Player(
        x=3.5,
        y=3.5,
        dir_x=-1.0,
        dir_y=0.0,
        plane_x=0.0,
        plane_y=FOV_SCALE,
    )

    running = True
    while running:
        dt = min(clock.tick(FPS_TARGET) / 1000.0, 0.05)

        running = handle_input(player, dt)

        # Draw ceiling and floor first.
        screen.fill(CEILING_COLOR)
        pygame.draw.rect(screen, FLOOR_COLOR, (0, HALF_HEIGHT, SCREEN_WIDTH, HALF_HEIGHT))

        # Raycast + draw world.
        cast_and_render_walls(screen, player)

        # 2D UI overlays.
        draw_minimap(screen, player)
        draw_hud(screen, clock, font)

        pygame.display.flip()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()


# ============================================================
# Raycasting math explanation (high-level)
# ============================================================
# 1) The world is a 2D grid map where each cell is empty or wall.
#
# 2) For every vertical screen column x, we create one ray:
#       camera_x = 2*x/width - 1
#       ray_dir  = player_dir + camera_plane * camera_x
#
#    - player_dir points where the player looks.
#    - camera_plane is perpendicular to player_dir and controls FOV.
#
# 3) DDA (Digital Differential Analysis):
#    We traverse grid squares along the ray by advancing to the next
#    vertical or horizontal grid boundary, whichever is closer.
#
#    - deltaDistX = abs(1/ray_dir_x)
#    - deltaDistY = abs(1/ray_dir_y)
#
#    sideDistX and sideDistY track distance to next x/y boundary.
#    Repeatedly advance the smaller one until a wall cell is hit.
#
# 4) Perpendicular distance (fisheye fix):
#    Raw ray length causes fisheye distortion. Instead we use the
#    distance projected onto the camera direction (perp distance).
#
# 5) Wall slice height:
#       line_height = screen_height / perp_wall_dist
#    Near walls are tall; far walls are short.
#
# 6) Render wall slice:
#    Draw a vertical line for this column from draw_start to draw_end.
#    Apply distance-based shading (farther = darker).
#
# Repeating this for all columns produces a pseudo-3D frame at runtime.
