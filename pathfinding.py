# https://www.redblobgames.com/pathfinding/a-star/implementation.html
# Apache v2 licensed by Red Blob Games.
import heapq
from globals import *

# skipping the type hinting for now
class SquareGrid:
    def __init__(self, grid, width, height):
        self.width = width
        self.height = height
        self.edges = {}
        self.walls = []


        for r in range(height):
            for c in range(width):
                if grid[r][c] not in WALKABLE:
                    self.walls.append((c, r))

    def in_bounds(self, id):
        (x, y) = id
        return 1 <= x < self.width-1 and 1 <= y < self.height-1

    def passable(self, id):
        return id not in self.walls

    def neighbors(self, id):
        (x, y) = id
        # neighbors = [(x+1, y), (x-1, y), (x, y-1), (x, y+1)] # E W N S
        # neighbors = [(x-1, y-1), (x, y-1), (x+1, y-1), (x+1, y), (x+1, y+1), (x, y+1), (x-1, y+1), (x-1, y)] # NW N NE E SE S SW W
        cardinal_dirs = [(x, y-1), (x+1, y), (x, y+1), (x-1, y)] # N E S W
        ordinal_dirs = [(x-1, y-1), (x+1, y-1), (x+1, y+1), (x-1, y+1)] # NW, NE, SE, SW
        neighbors = [*cardinal_dirs, *ordinal_dirs] # NW N NE E SE S SW W

        # TBD - figure out a way to identify which neighbors are cardinal/ordinal for cost bias

        if (x + y) % 2 == 0: neighbors.reverse() # S N W E

        results = filter(self.in_bounds, neighbors)
        results = filter(self.passable, results)
        return results

class GridWithWeights(SquareGrid):
    def __init__(self, grid, width, height):
        super().__init__(grid, width, height)
        self.weights = {}

    def cost(self, from_node, to_node):
        return self.weights.get(to_node, 1)

class PriorityQueue:
    def __init__(self):
        self.elements = []

    def empty(self):
        return not self.elements
    
    def put(self, item, priority):
        heapq.heappush(self.elements, (priority, item))

    def get(self):
        return heapq.heappop(self.elements)[1]

def dijkstra_search(graph, start, goal):
    frontier = PriorityQueue()
    frontier.put(start, 0)

    came_from = {}
    came_from[start] = None

    cost_so_far = {}
    cost_so_far[start] = 0

    while not frontier.empty():
        current = frontier.get()

        if current == goal: # early exit
            break

        for next in graph.neighbors(current):
            new_cost = cost_so_far[current] + graph.cost(current, next)
            if next not in cost_so_far or new_cost < cost_so_far[next]:
                cost_so_far[next] = new_cost
                priority = new_cost
                frontier.put(next, priority)
                came_from[next] = current

    return came_from, cost_so_far

# build a path from start to goal
def reconstruct_path(came_from, start, goal):
    current = goal
    path = []

    if goal not in came_from:
        return []

    while current != start:
        path.append(current)
        current = came_from[current]

    path.append(start)
    path.reverse()
    return path

# A*
def heuristic(a, b):
    (x1, y1) = a
    (x2, y2) = b
    return abs(x1 - x2) + abs(y1 - y2)

def a_star_search(graph, start, goal):
    frontier = PriorityQueue()
    frontier.put(start, 0)

    came_from = {}
    came_from[start] = None

    cost_so_far = {}
    cost_so_far[start] = 0

    while not frontier.empty():
        current = frontier.get()

        if current == goal:
            break

        for next in graph.neighbors(current):
            new_cost = cost_so_far[current] + graph.cost(current, next)

            if next not in cost_so_far or new_cost < cost_so_far[next]:
                cost_so_far[next] = new_cost
                priority = new_cost + heuristic(next, goal)
                frontier.put(next, priority)
                came_from[next] = current

    return came_from, cost_so_far



    
"""
import random
g = GridWithWeights(30, 15)
g.walls = []
for r in range(15):
    g.walls.append([])
    for c in range(30):
        if r == 0 or r == 14 or c == 0 or c == 29:
            g.walls[r].append("WALL")
        else:
            if random.random() > 0.8:
                g.walls[r].append("WALL")
            else:
                g.walls[r].append("EMPTY")

done = False
while not done:
    start = (random.randint(1,29), random.randint(1,14))
    end = (random.randint(1,29), random.randint(1,14))
    if g.passable(start) and g.passable(end) and start != end:
        done = True


# came_from, cost_so_far = dijkstra_search(g, start, end)
came_from, cost_so_far = a_star_search(g, start, end)
path = reconstruct_path(came_from, start, end)

for r in range(15):
    op = ""
    for c in range(30):
        if start[0] == c and start[1] == r:
            op += " @"
        elif end[0] == c and end[1] == r:
            op += " R"
        else:
            if g.walls[r][c] == "WALL":
                op += " #"
            else:
                id = (c, r)
                # if id in path:
                #     op += " r"
                if id in cost_so_far:
                    op += "%2s" % str(cost_so_far[id])
                else:
                    op += "  "
    print(op)

# print(cost_so_far)

# start, goal = (1, 4), (8, 3)
# came_from, cost_so_far = dijkstra_search(diagram4, start, goal)
# cost_so_far can use as a distance field for nearness without path building
"""